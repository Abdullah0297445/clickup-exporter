import asyncio
import json

from django.utils import timezone
from django.core.cache import cache

from celery import shared_task

from export import config
from export.cache import get_current_cache_version, get_old_cache_version
from export.clickup_data_fetcher import export_clickup_data
from export.exceptions import ExportError, ClickupTeamIDMissing


@shared_task(bind=True, retry_backoff=5, max_retries=5, retry_jitter=True)
def fetch_clickup_data_and_persist(self) -> dict:
    team_id = config.CLICKUP_TEAM_ID
    if not team_id:
        raise ClickupTeamIDMissing()

    version = get_current_cache_version()
    lock_key = f"lock:{team_id}"

    got_lock = False
    try:
        got_lock = cache.add(lock_key, "1", timeout=config.REDIS_LOCK_TTL)
        if not got_lock:
            return {"status": "in_progress"}

        if cache.get(team_id, version=version):
            return {"status": "success"}

        meta = {"status": "in_progress", "started_at": timezone.now().isoformat()}
        cache.set(team_id, json.dumps(meta), version=version)

        try:
            payload = asyncio.run(export_clickup_data(team_id))
        except ExportError as ee:
            err_meta = {
                "status": "error",
                "error": ee.message,
                "status_code": getattr(ee, "status", None),
                "updated_at": timezone.now().isoformat()
            }
            cache.set(team_id, json.dumps(err_meta), version=version)
            raise
        except Exception:
            try:
                raise
            except Exception as exc:
                raise self.retry(exc=exc)
        store = {
            "status": "success",
            "data": payload,
            "updated_at": timezone.now().isoformat(),
        }
        cache.set(team_id, json.dumps(store), version=version)
        cache.delete(team_id, version=get_old_cache_version())
        return {"status": "success"}
    finally:
        try:
            if got_lock:
                cache.delete(lock_key)
        except Exception:
            pass
