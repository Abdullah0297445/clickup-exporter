import asyncio
import httpx
from django.utils import timezone
from typing import Any, Optional

from export.exceptions import ExportError
from export.config import CLICKUP_TOKEN, CLICKUP_TEAM_ID, CONCURRENCY, MAX_RETRIES, INITIAL_BACKOFF


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
        params = {"page": page, "include_closed": "true"}
        url = f"{BASE}/list/{list_id}/task"
        data = await request_with_retry(client, "GET", url, params=params)
        tasks = data.get("tasks", []) if data else []
        if not tasks:
            break
        all_tasks.extend(tasks)
        if data.get("last_page"):
            break
        page += 1
    return all_tasks


async def get_time_entries_for_list(
    client: httpx.AsyncClient, team_id: str, list_id: str, member_ids: list[str]
) -> list[dict]:
    all_entries: list[dict] = []
    params: dict[str, Any] = {
        "list_id": list_id,
        "start": 1735671600000,
        "end": int(timezone.now().timestamp() * 1000),
        "assignee": ",".join(member_ids),
        "include_location_names": True
    }
    url = f"{BASE}/team/{team_id}/time_entries"
    data = await request_with_retry(client, "GET", url, params=params)
    entries = data.get("data", []) if data else []
    all_entries.extend(entries)
    return all_entries


async def get_spaces(client: httpx.AsyncClient, team_id: str) -> list[dict]:
    url = f"{BASE}/team/{team_id}/space"
    data = await request_with_retry(client, "GET", url)
    return data.get("spaces", []) if data else []


async def get_lists_for_space(client: httpx.AsyncClient, space_id: str) -> list[dict]:
    url = f"{BASE}/space/{space_id}/list"
    data = await request_with_retry(client, "GET", url)
    return data.get("lists", []) if data else []


async def get_lists_for_folder(client: httpx.AsyncClient, space_id: str) -> list[dict]:
    url = f"{BASE}/space/{space_id}/folder"
    data = await request_with_retry(client, "GET", url)
    lists = []
    if data.get("folders"):
        for f in data["folders"]:
            lists.extend(f.get("lists", []))
    return lists


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
        try:
            task_id = e["task"]["id"]
        except KeyError:
            continue
        user_id = e["user"]["id"]
        username = e["user"]["username"]
        duration = e["duration"]
        billable = e["billable"]

        task_bucket = agg.setdefault(task_id, {})
        user_bucket = task_bucket.setdefault(user_id, {"assignee_name": username, "billable_ms": 0, "non_billable_ms": 0})
        if billable:
            user_bucket["billable_ms"] += int(duration)
        else:
            user_bucket["non_billable_ms"] += int(duration)

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
    lst: dict,
    member_ids: list[str]
) -> tuple[list[dict], list[dict]]:
    async with sem:
        list_id = str(lst.get("id"))
        tasks = await paginate_list_tasks(client, list_id)
        tasks_with_space_name = []
        for t in tasks:
            t["space"]["name"] = lst["space"]["name"]
            tasks_with_space_name.append(t)
        time_entries = await get_time_entries_for_list(client, team_id, list_id, member_ids)
        return tasks, time_entries


async def export_clickup_data(team_id: Optional[str] = None) -> list[dict]:
    team_id = team_id or CLICKUP_TEAM_ID
    if CLICKUP_TOKEN.startswith("pk_YOUR") or str(team_id).startswith("YOUR"):
        raise ExportError(400, "Please set CLICKUP_TOKEN and CLICKUP_TEAM_ID (or pass team_id).")

    concurrency = CONCURRENCY
    sem = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(max_connections=concurrency, max_keepalive_connections=5)

    async with httpx.AsyncClient(limits=limits, headers=HEADERS) as client:
        spaces = await get_spaces(client, team_id)
        member_ids: list[str] = []

        for s in spaces:
            if s.get("members"):
                for m in s["members"]:
                    member_ids.append(str(m["user"]["id"]))

        all_lists: list[dict] = []
        list_fetch_coros = [get_lists_for_space(client, s["id"]) for s in spaces]
        folder_coros = [get_lists_for_folder(client, s["id"]) for s in spaces]
        lists_results = await asyncio.gather(*list_fetch_coros)
        folder_lists_results = await asyncio.gather(*folder_coros)

        for l in lists_results:
            all_lists.extend(l)
        for l in folder_lists_results:
            all_lists.extend(l)

        seen = set()
        deduped_lists = []
        for l in all_lists:
            lid = str(l.get("id"))
            if lid not in seen:
                deduped_lists.append(l)
                seen.add(lid)

        tasks_coros = [process_list_worker(sem, client, team_id, lst, member_ids) for lst in deduped_lists]

        CHUNK = min(10, concurrency)
        results = []
        for i in range(0, len(tasks_coros), CHUNK):
            chunk = tasks_coros[i : i + CHUNK]
            chunk_res = await asyncio.gather(*chunk)
            results.extend(chunk_res)

        all_tasks: list[dict] = []
        all_time_entries: list[dict] = []
        for tasks, time_entries in results:
            all_tasks.extend(tasks)
            all_time_entries.extend(time_entries)

        task_time_summary = aggregate_time_entries_by_task(all_time_entries)

        tasks_with_time_summary: list[dict] = []
        for t in all_tasks:
            t["time_summary"] = task_time_summary.get(t["id"], list())
            tasks_with_time_summary.append(t)

        return tasks_with_time_summary
