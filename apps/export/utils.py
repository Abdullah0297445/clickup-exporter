from django.http import JsonResponse, HttpRequest

from export import config
from django.core.cache import cache


def verify_bearer_token(request: HttpRequest):
    if not config.API_AUTH_TOKEN:
        return False, JsonResponse({"detail": "Server not configured"}, status=500)

    token_src = None
    for key in ("token", "api_token", "authorization"):
        val = request.GET.get(key)
        if val:
            token_src = val
            break

    if not token_src:
        return False, JsonResponse({"detail": "Missing token query parameter"}, status=401)

    parts = token_src.split()
    token = parts[1] if len(parts) >= 2 else parts[-1]

    if token != config.API_AUTH_TOKEN:
        return False, JsonResponse({"detail": "Invalid token"}, status=401)

    return True, None


def get_all_keys(team_id) -> list:
    key_pattern = cache.make_and_validate_key(key=team_id, version="*")
    keys = [k.decode() for k in cache._cache.get_client(key_pattern).scan_iter(match=key_pattern)]
    return keys


def get_earliest_version(team_id):
    keys = get_all_keys(team_id)

    if len(keys) <= config.KEEP_LAST_N_EXPORTS:
        return None

    try:
        earliest = min(keys)
    except ValueError:
        return None

    return earliest.split(":")[1]


def get_latest_version(team_id):
    keys = get_all_keys(team_id)

    try:
        latest = max(keys)
    except ValueError:
        return None

    return latest.split(":")[1]
