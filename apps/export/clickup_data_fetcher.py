import asyncio
import httpx
from django.utils import timezone
from typing import Any, Optional

from export.exceptions import ExportError
from export.config import CLICKUP_TOKEN, CLICKUP_TEAM_ID, CONCURRENCY, MAX_RETRIES, PAGE_SIZE, INITIAL_BACKOFF


BASE = "https://api.clickup.com/api/v2"
HEADERS = {"Authorization": CLICKUP_TOKEN, "Accept": "application/json", "Accept-Encoding": "gzip, deflate, br"}


async def request_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    params: Optional[dict] = None,
    json_body: Optional[dict] = None,
    max_retries: int = MAX_RETRIES,
) -> Optional[dict]:
    attempt = 0
    backoff = INITIAL_BACKOFF
    while True:
        attempt += 1
        try:
            resp = await client.request(method, url, params=params, json=json_body, timeout=30.0)
        except (httpx.RequestError, httpx.HTTPError) as e:
            if attempt >= max_retries:
                raise ExportError(502, f"Network error: {e}")
            await asyncio.sleep(backoff)
            backoff *= 2
            continue

        if resp.status_code in (200, 201):
            try:
                return resp.json()
            except Exception:
                return None
        elif resp.status_code == 204:
            return None
        elif resp.status_code == 429:
            ra = resp.headers.get("Retry-After")
            wait = float(ra) if ra else backoff
            await asyncio.sleep(wait + (backoff * 0.1))
            backoff *= 2
            if attempt >= max_retries:
                raise ExportError(429, "Rate limited by ClickUp and max retries exceeded")
            continue
        elif 500 <= resp.status_code < 600:
            if attempt >= max_retries:
                raise ExportError(502, f"ClickUp server error {resp.status_code}")
            await asyncio.sleep(backoff)
            backoff *= 2
            continue
        else:
            # Unexpected client error
            raise ExportError(resp.status_code, f"ClickUp API error: {resp.text}")


async def paginate_list_tasks(client: httpx.AsyncClient, list_id: str) -> list[dict]:
    page = 0
    all_tasks: list[dict] = []
    while True:
        params = {"page": page, "limit": PAGE_SIZE, "include_closed": "true"}
        url = f"{BASE}/list/{list_id}/task"
        data = await request_with_retry(client, "GET", url, params=params)
        tasks = data.get("tasks", []) if data else []
        if not tasks:
            break
        all_tasks.extend(tasks)
        if len(tasks) < PAGE_SIZE:
            break
        page += 1
    return all_tasks


async def paginate_time_entries_for_list(
    client: httpx.AsyncClient, team_id: str, list_id: str
) -> list[dict]:
    page = 0
    all_entries: list[dict] = []
    while True:
        params: dict[str, Any] = {
            "list_id": list_id,
            "page": page,
            "start": 1735671600000,
            "end": int(timezone.now().timestamp() * 1000),
        }
        url = f"{BASE}/team/{team_id}/time_entries"
        data = await request_with_retry(client, "GET", url, params=params)
        entries = data.get("time_entries", []) if data else []
        if not entries:
            break
        all_entries.extend(entries)
        if len(entries) < PAGE_SIZE:
            break
        page += 1
    return all_entries


async def get_spaces(client: httpx.AsyncClient, team_id: str) -> list[dict]:
    url = f"{BASE}/team/{team_id}/space"
    data = await request_with_retry(client, "GET", url)
    return data.get("spaces", []) if data else []


async def get_lists_for_space(client: httpx.AsyncClient, space_id: str) -> list[dict]:
    url = f"{BASE}/space/{space_id}/list"
    data = await request_with_retry(client, "GET", url)
    return data.get("lists", []) if data else []


async def get_lists_for_folder(client: httpx.AsyncClient, folder_id: str) -> list[dict]:
    url = f"{BASE}/folder/{folder_id}/list"
    data = await request_with_retry(client, "GET", url)
    return data.get("lists", []) if data else []


def ms_to_hours(ms: Optional[int]) -> Optional[float]:
    if ms is None:
        return None
    try:
        return round((ms / 1000.0) / 3600.0, 4)
    except Exception:
        return None


def aggregate_time_entries_by_task(entries: list[dict]) -> dict[str, list[dict]]:
    agg: dict[str, dict[str, dict[str, Any]]] = {}
    for e in entries:
        task_id = e.get("task_id") or (e.get("task") or {}).get("id")
        if not task_id:
            continue
        user = e.get("user") or {}
        user_id = user.get("id") or e.get("user_id") or "unknown_user"
        username = user.get("username") or user.get("email") or user.get("name") or str(user_id)
        duration = e.get("duration") or 0
        billable_flag = e.get("billable")
        billable = bool(billable_flag) if billable_flag is not None else False

        task_bucket = agg.setdefault(task_id, {})
        user_bucket = task_bucket.setdefault(user_id, {"assignee_name": username, "billable_ms": 0, "non_billable_ms": 0})
        if billable:
            user_bucket["billable_ms"] += duration
        else:
            user_bucket["non_billable_ms"] += duration

    result: dict[str, list[dict]] = {}
    for task_id, users in agg.items():
        lst = []
        for uid, v in users.items():
            lst.append(
                {
                    "assignee_id": uid,
                    "assignee_name": v["assignee_name"],
                    "billable_ms": v["billable_ms"],
                    "non_billable_ms": v["non_billable_ms"],
                    "billable_hours": ms_to_hours(v["billable_ms"]),
                    "non_billable_hours": ms_to_hours(v["non_billable_ms"]),
                }
            )
        result[task_id] = lst
    return result


async def process_list_worker(
    sem: asyncio.Semaphore,
    client: httpx.AsyncClient,
    team_id: str,
    lst: dict
) -> tuple[str, list[dict], list[dict], dict]:
    async with sem:
        list_id = str(lst.get("id"))
        tasks = await paginate_list_tasks(client, list_id)
        time_entries = await paginate_time_entries_for_list(client, team_id, list_id)

        meta = {
            "list_id": list_id,
            "list_name": lst.get("name"),
            "space_id": lst.get("_space_id") or lst.get("space_id"),
            "space_name": lst.get("_space_name") or lst.get("_space_name") or lst.get("space_name"),
            "folder_id": lst.get("_folder_id"),
            "folder_name": lst.get("_folder_name"),
        }
        for t in tasks:
            t["_source_list_id"] = meta["list_id"]
            t["_source_list_name"] = meta["list_name"]
            t["_source_space_id"] = meta["space_id"]
            t["_source_space_name"] = meta["space_name"]
            if meta.get("folder_id"):
                t["_source_folder_id"] = meta["folder_id"]
                t["_source_folder_name"] = meta["folder_name"]

        for te in time_entries:
            te["_queried_list_id"] = list_id

        return list_id, tasks, time_entries, meta


async def export_clickup_data(team_id: Optional[str] = None) -> list[dict]:
    team_id = team_id or CLICKUP_TEAM_ID
    if CLICKUP_TOKEN.startswith("pk_YOUR") or str(team_id).startswith("YOUR"):
        raise ExportError(400, "Please set CLICKUP_TOKEN and CLICKUP_TEAM_ID (or pass team_id).")

    concurrency = CONCURRENCY
    sem = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=10)

    async with httpx.AsyncClient(limits=limits, headers=HEADERS) as client:
        spaces = await get_spaces(client, team_id)

        # fetch lists for each space
        list_fetch_coros = [get_lists_for_space(client, str(s.get("id"))) for s in spaces]
        lists_results = await asyncio.gather(*list_fetch_coros)
        lists_all: list[dict] = []
        for sp, lists in zip(spaces, lists_results):
            for lst in lists:
                lst["_space_id"] = str(sp.get("id"))
                lst["_space_name"] = sp.get("name")
                lists_all.append(lst)
            folders = sp.get("folders") or []
            if folders:
                folder_coros = [get_lists_for_folder(client, str(f.get("id"))) for f in folders]
                folder_lists_results = await asyncio.gather(*folder_coros)
                for folder_obj, folder_lists in zip(folders, folder_lists_results):
                    for fl in folder_lists:
                        fl["_space_id"] = str(sp.get("id"))
                        fl["_space_name"] = sp.get("name")
                        fl["_folder_id"] = str(folder_obj.get("id"))
                        fl["_folder_name"] = folder_obj.get("name")
                        lists_all.append(fl)

        # dedupe
        seen = set()
        deduped_lists = []
        for l in lists_all:
            lid = str(l.get("id"))
            if lid not in seen:
                deduped_lists.append(l)
                seen.add(lid)

        tasks_coros = [process_list_worker(sem, client, team_id, lst) for lst in deduped_lists]

        CHUNK = max(10, concurrency)
        results = []
        for i in range(0, len(tasks_coros), CHUNK):
            chunk = tasks_coros[i : i + CHUNK]
            chunk_res = await asyncio.gather(*chunk)
            results.extend(chunk_res)

        all_tasks: list[dict] = []
        all_time_entries: list[dict] = []
        list_meta_map: dict[str, dict] = {}
        for list_id, tasks, time_entries, meta in results:
            list_meta_map[list_id] = meta
            all_tasks.extend(tasks)
            all_time_entries.extend(time_entries)

        task_time_summary = aggregate_time_entries_by_task(all_time_entries)

        flattened: list[dict] = []
        for t in all_tasks:
            task_id = t.get("id")
            name = t.get("name")
            status = t.get("status") or {}
            status_text = status.get("status") if isinstance(status, dict) else status
            assignees = t.get("assignees") or []
            assignees_text = "; ".join([a.get("username") or str(a.get("id")) for a in assignees])
            due_date = t.get("due_date")
            date_created = t.get("date_created")
            time_estimate_ms = t.get("time_estimate") or None
            time_spent_ms = t.get("time_spent") or None
            time_estimate_hours = ms_to_hours(time_estimate_ms)
            time_spent_hours = ms_to_hours(time_spent_ms)
            source_list_id = t.get("_source_list_id")
            source_list_name = t.get("_source_list_name")
            source_space_id = t.get("_source_space_id")
            source_space_name = t.get("_source_space_name")
            custom_fields = t.get("custom_fields") or []
            time_summary = task_time_summary.get(task_id, [])

            flattened.append(
                {
                    "id": task_id,
                    "name": name,
                    "status": status_text,
                    "assignees_text": assignees_text,
                    "due_date": due_date,
                    "date_created": date_created,
                    "time_estimate_ms": time_estimate_ms,
                    "time_estimate_hours": time_estimate_hours,
                    "time_spent_ms": time_spent_ms,
                    "time_spent_hours": time_spent_hours,
                    "source_list_id": source_list_id,
                    "source_list_name": source_list_name,
                    "source_space_id": source_space_id,
                    "source_space_name": source_space_name,
                    "custom_fields": custom_fields,
                    "time_summary": time_summary,
                }
            )

        return flattened
