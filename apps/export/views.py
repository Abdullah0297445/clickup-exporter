import json

from django.conf import settings
from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_GET, require_POST
from django.core.cache import cache

from export import config
from export.cache import get_current_cache_version


def _verify_bearer_token(request: HttpRequest):
    if not config.API_AUTH_TOKEN:
        return False, JsonResponse({"detail": "Server not configured"}, status=500)
    auth = request.headers.get("authorization") or request.META.get("HTTP_AUTHORIZATION")
    if not auth:
        return False, JsonResponse({"detail": "Missing Authorization header"}, status=401)
    parts = auth.split()
    token = parts[1] if len(parts) >= 2 else parts[-1]
    if token != config.API_AUTH_TOKEN:
        return False, JsonResponse({"detail": "Invalid token"}, status=401)
    return True, None


@require_GET
def export(request: HttpRequest):
    ok, resp = _verify_bearer_token(request)
    if not ok:
        return resp

    team_id = config.CLICKUP_TEAM_ID
    if not team_id:
        return JsonResponse({"detail": "team_id missing"}, status=400)

    raw = cache.get(team_id, version=get_current_cache_version())
    if not raw:
        return JsonResponse({"status": "not_ready", "detail": "No cached export available"}, status=202)
    try:
        data = json.loads(raw)
    except Exception:
        return JsonResponse({"status": "error", "detail": "Invalid cached data"}, status=500)

    if isinstance(data, dict) and data.get("status") == "success" and "data" in data:
        return JsonResponse(data["data"], status=200, safe=False)

    return JsonResponse(data, status=200, safe=False)
