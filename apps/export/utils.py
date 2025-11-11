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


def get_all_keys(team_id):
    key_pattern = cache.make_and_validate_key(key=team_id, version="*")
    keys = [k.decode for k in cache._cache.get_client(key_pattern).scan_iter(match=key_pattern)]
    return keys


def get_earliest_version(team_id):
    try:
        keys = get_all_keys(team_id)
        if len(keys) <= config.KEEP_LAST_N_EXPORTS:
            return None
        return min(get_all_keys(team_id)).split(":")[1]
    except ValueError:
        return None


def get_latest_version(team_id):
    try:
        return max(get_all_keys(team_id)).split(":")[1]
    except ValueError:
        return None
