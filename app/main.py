# clickup_export_semaphore.py
#
# FastAPI service that exports ClickUp tasks + aggregated time tracking.
# - Uses ClickUp API v2 endpoints: /team/{team_id}/space, /space/{space_id}/list,
#   /folder/{folder_id}/list, /list/{list_id}/task, /team/{team_id}/time_entries
# - Async + controlled concurrency using asyncio.Semaphore (semaphore pattern)
# - Per-list pagination is handled sequentially; lists are processed in parallel up to `CONCURRENCY`
# - Aggregates time tracked per task per assignee with billable/non-billable split
#
# Usage:
#  1) pip install fastapi "uvicorn[standard]" httpx python-dotenv
#  2) set env vars CLICKUP_TOKEN and CLICKUP_TEAM_ID (or pass team_id in request body)
#  3) run: uvicorn clickup_export_semaphore:app --reload
#  4) POST /export with optional JSON to control time window / concurrency / output path
#
# Notes & tuning:
#  - Keep CONCURRENCY conservative (10-30) for reliability; increase if your org is small and network is great.
#  - Respect ClickUp rate limits; this script handles 429 via Retry-After header and simple backoff.
#  - For very large orgs (many lists/tasks), prefer chunking or a queue worker approach to avoid memory spikes.
# -----------------------------------------------------------------------------

import os
import asyncio
import csv
import json
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, UTC

import httpx
from fastapi import FastAPI, HTTPException, Body
from pydantic import BaseModel


# -----------------------
# Configuration (env or defaults)
# -----------------------
CLICKUP_TOKEN = os.getenv("CLICKUP_TOKEN", "pk_YOUR_CLICKUP_TOKEN_HERE")
CLICKUP_TEAM_ID = os.getenv("CLICKUP_TEAM_ID", "YOUR_TEAM_ID_HERE")
PAGE_SIZE = int(os.getenv("PAGE_SIZE", "100"))
CONCURRENCY = int(os.getenv("CONCURRENCY", "8"))
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "5"))
INITIAL_BACKOFF = float(os.getenv("INITIAL_BACKOFF", "1.0"))

BASE = "https://api.clickup.com/api/v2"
HEADERS = {"Authorization": CLICKUP_TOKEN, "Accept": "application/json"}

app = FastAPI(title="ClickUp Export (Semaphore Parallelism)")


# -----------------------
# HTTP helper with retry/429 handling
# -----------------------
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
                raise HTTPException(status_code=502, detail=f"Network error: {str(e)}")
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
            # Rate limit: respect Retry-After if present
            ra = resp.headers.get("Retry-After")
            wait = float(ra) if ra else backoff
            # small jitter
            await asyncio.sleep(wait + (backoff * 0.1))
            backoff *= 2
            if attempt >= max_retries:
                raise HTTPException(status_code=429, detail="Rate limited by ClickUp (429) and max retries exceeded")
            continue
        elif 500 <= resp.status_code < 600:
            if attempt >= max_retries:
                raise HTTPException(status_code=502, detail=f"ClickUp server error {resp.status_code}")
            await asyncio.sleep(backoff)
            backoff *= 2
            continue
        else:
            # client error - bubble up
            raise HTTPException(status_code=resp.status_code, detail=f"ClickUp API error: {resp.text}")


# -----------------------
# Pagination helpers (per-list sequential)
# -----------------------
async def paginate_list_tasks(client: httpx.AsyncClient, list_id: str, include_closed: bool = True) -> List[dict]:
    page = 0
    all_tasks: List[dict] = []
    while True:
        params = {"page": page, "limit": PAGE_SIZE}
        if include_closed:
            params["include_closed"] = "true"
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
    client: httpx.AsyncClient, team_id: str, list_id: str, start_ms: Optional[int] = None, end_ms: Optional[int] = None
) -> List[dict]:
    page = 0
    all_entries: List[dict] = []
    while True:
        params: Dict[str, Any] = {"list_id": list_id, "page": page}
        if start_ms is not None:
            params["start"] = start_ms
        if end_ms is not None:
            params["end"] = end_ms
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


# -----------------------
# High-level ClickUp collectors
# -----------------------
async def get_spaces(client: httpx.AsyncClient, team_id: str) -> List[dict]:
    url = f"{BASE}/team/{team_id}/space"
    data = await request_with_retry(client, "GET", url)
    return data.get("spaces", []) if data else []


async def get_lists_for_space(client: httpx.AsyncClient, space_id: str) -> List[dict]:
    url = f"{BASE}/space/{space_id}/list"
    data = await request_with_retry(client, "GET", url)
    return data.get("lists", []) if data else []


async def get_lists_for_folder(client: httpx.AsyncClient, folder_id: str) -> List[dict]:
    url = f"{BASE}/folder/{folder_id}/list"
    data = await request_with_retry(client, "GET", url)
    return data.get("lists", []) if data else []


# -----------------------
# Utilities for aggregation
# -----------------------
def ms_to_hours(ms: Optional[int]) -> Optional[float]:
    if ms is None:
        return None
    try:
        return round((ms / 1000.0) / 3600.0, 4)
    except Exception:
        return None


def aggregate_time_entries_by_task(entries: List[dict]) -> Dict[str, List[dict]]:
    """
    Returns mapping: task_id -> list of {assignee_id, assignee_name, billable_ms, non_billable_ms}
    """
    agg: Dict[str, Dict[str, Dict[str, Any]]] = {}

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

    result: Dict[str, List[dict]] = {}
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


# -----------------------
# Request model for /export
# -----------------------
class ExportRequest(BaseModel):
    team_id: Optional[str] = None
    include_closed: Optional[bool] = True
    time_start_ms: Optional[int] = None
    time_end_ms: Optional[int] = None
    output_csv_path: Optional[str] = None
    concurrency: Optional[int] = None  # override CONCURRENCY for this run


# -----------------------
# Semaphore-wrapped per-list worker
# -----------------------
async def process_list_worker(
    sem: asyncio.Semaphore,
    client: httpx.AsyncClient,
    team_id: str,
    lst: dict,
    include_closed: bool,
    time_start_ms: Optional[int],
    time_end_ms: Optional[int],
) -> Tuple[str, List[dict], List[dict], dict]:
    """
    Acquire semaphore, fetch all tasks for a list (paginated) and its time entries.
    Returns (list_id, tasks, time_entries, metadata)
    """
    async with sem:
        list_id = str(lst.get("id"))
        # sequential pagination inside this function
        tasks = await paginate_list_tasks(client, list_id, include_closed=include_closed)
        time_entries = await paginate_time_entries_for_list(client, team_id, list_id, start_ms=time_start_ms, end_ms=time_end_ms)

        meta = {
            "list_id": list_id,
            "list_name": lst.get("name"),
            "space_id": lst.get("_space_id") or lst.get("space_id"),
            "space_name": lst.get("_space_name") or lst.get("_space_name") or lst.get("space_name"),
            "folder_id": lst.get("_folder_id"),
            "folder_name": lst.get("_folder_name"),
        }
        # annotate tasks with metadata for easy flattening
        for t in tasks:
            t["_source_list_id"] = meta["list_id"]
            t["_source_list_name"] = meta["list_name"]
            t["_source_space_id"] = meta["space_id"]
            t["_source_space_name"] = meta["space_name"]
            if meta.get("folder_id"):
                t["_source_folder_id"] = meta["folder_id"]
                t["_source_folder_name"] = meta["folder_name"]

        # annotate time entries with a queried list id for traceability
        for te in time_entries:
            te["_queried_list_id"] = list_id

        return list_id, tasks, time_entries, meta


# -----------------------
# Export endpoint
# -----------------------
@app.post("/export")
async def export_clickup(req: ExportRequest = Body(...)):
    team_id = req.team_id or CLICKUP_TEAM_ID
    if CLICKUP_TOKEN.startswith("pk_YOUR") or team_id.startswith("YOUR"):
        raise HTTPException(status_code=400, detail="Please set CLICKUP_TOKEN and CLICKUP_TEAM_ID (or pass team_id in request body).")

    concurrency = req.concurrency or CONCURRENCY
    sem = asyncio.Semaphore(concurrency)

    limits = httpx.Limits(max_connections=concurrency + 10, max_keepalive_connections=10)
    async with httpx.AsyncClient(limits=limits, headers=HEADERS) as client:
        # 1) gather spaces
        spaces = await get_spaces(client, team_id)

        # 2) gather lists for each space (in parallel, but limited)
        # We'll fetch lists for spaces concurrently but small in number typically.
        list_fetch_coros = [get_lists_for_space(client, str(s.get("id"))) for s in spaces]
        lists_results = await asyncio.gather(*list_fetch_coros)
        lists_all: List[dict] = []
        for sp, lists in zip(spaces, lists_results):
            for lst in lists:
                lst["_space_id"] = str(sp.get("id"))
                lst["_space_name"] = sp.get("name")
                lists_all.append(lst)
            # also handle folders in the space
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

        # dedupe lists by id
        seen = set()
        deduped_lists = []
        for l in lists_all:
            lid = str(l.get("id"))
            if lid not in seen:
                deduped_lists.append(l)
                seen.add(lid)

        # 3) Kick off a worker for each list but controlled by semaphore
        tasks_coros = [
            process_list_worker(sem, client, team_id, lst, req.include_closed, req.time_start_ms, req.time_end_ms)
            for lst in deduped_lists
        ]

        # run coroutines in chunks to avoid creating thousands at once (safer)
        CHUNK = max(10, concurrency)
        results = []
        for i in range(0, len(tasks_coros), CHUNK):
            chunk = tasks_coros[i : i + CHUNK]
            chunk_res = await asyncio.gather(*chunk)
            results.extend(chunk_res)

        # 4) Collect tasks & time entries and metadata
        all_tasks: List[dict] = []
        all_time_entries: List[dict] = []
        list_meta_map: Dict[str, dict] = {}
        for list_id, tasks, time_entries, meta in results:
            list_meta_map[list_id] = meta
            all_tasks.extend(tasks)
            all_time_entries.extend(time_entries)

        # 5) Aggregate time entries
        task_time_summary = aggregate_time_entries_by_task(all_time_entries)

        # 6) Build flattened task records
        flattened: List[dict] = []
        for t in all_tasks:
            task_id = t.get("id")
            name = t.get("name")
            status = t.get("status") or {}
            status_text = status.get("status") if isinstance(status, dict) else status
            assignees = t.get("assignees") or []
            assignees_text = "; ".join([a.get("username") or a.get("id") for a in assignees])
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

        # 7) Optionally write CSV
        if req.output_csv_path:
            csv_path = req.output_csv_path
            with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
                headers = [
                    "id",
                    "name",
                    "status",
                    "assignees_text",
                    "due_date",
                    "date_created",
                    "time_estimate_ms",
                    "time_estimate_hours",
                    "time_spent_ms",
                    "time_spent_hours",
                    "source_list_id",
                    "source_list_name",
                    "source_space_id",
                    "source_space_name",
                    "custom_fields_json",
                    "time_summary_json",
                ]
                writer = csv.DictWriter(f, fieldnames=headers)
                writer.writeheader()
                for rec in flattened:
                    writer.writerow(
                        {
                            "id": rec["id"],
                            "name": rec["name"],
                            "status": rec["status"],
                            "assignees_text": rec["assignees_text"],
                            "due_date": rec["due_date"],
                            "date_created": rec["date_created"],
                            "time_estimate_ms": rec["time_estimate_ms"],
                            "time_estimate_hours": rec["time_estimate_hours"],
                            "time_spent_ms": rec["time_spent_ms"],
                            "time_spent_hours": rec["time_spent_hours"],
                            "source_list_id": rec["source_list_id"],
                            "source_list_name": rec["source_list_name"],
                            "source_space_id": rec["source_space_id"],
                            "source_space_name": rec["source_space_name"],
                            "custom_fields_json": json.dumps(rec["custom_fields"], ensure_ascii=False),
                            "time_summary_json": json.dumps(rec["time_summary"], ensure_ascii=False),
                        }
                    )
            return {"status": "ok", "written_csv": csv_path, "task_count": len(flattened)}

        # else return JSON (can be large)
        return {"status": "ok", "task_count": len(flattened), "tasks": flattened}


# -----------------------
# Health
# -----------------------
@app.get("/health")
async def health():
    return {"status": "ok", "time": datetime.now(tz=UTC).isoformat() + "Z"}
