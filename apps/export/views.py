from django.http import JsonResponse, HttpRequest
from django.views.decorators.http import require_GET
from django.core.cache import cache

from export import config
from export.utils import verify_bearer_token, get_latest_version


@require_GET
def export(request: HttpRequest):
    ok, resp = verify_bearer_token(request)
    if not ok:
        return resp

    team_id = config.CLICKUP_TEAM_ID
    if not team_id:
        return JsonResponse({"detail": "team_id missing"}, status=400)

    data = cache.get(team_id, version=get_latest_version(team_id))
    if not data:
        return JsonResponse({"status": "not_ready", "detail": "No cached export available"}, status=202)

    if data.get("status") == "success" and "data" in data:
        return JsonResponse(data["data"], status=200, safe=False)

    return JsonResponse(data, status=200, safe=False)
