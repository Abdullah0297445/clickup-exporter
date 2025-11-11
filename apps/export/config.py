import os
from django.conf import settings as project_settings
from django.apps import apps

app_config = apps.get_containing_app_config(__name__)

PREFIX = f"{app_config.name.upper()}_"

def _get(name, default):
    return getattr(project_settings, f"{PREFIX}{name}", default)


CLICKUP_TOKEN = _get("CLICKUP_TOKEN", os.getenv("CLICKUP_TOKEN", "pk_YOUR_CLICKUP_TOKEN_HERE"))
CLICKUP_TEAM_ID = _get("CLICKUP_TEAM_ID", os.getenv("CLICKUP_TEAM_ID", "YOUR_TEAM_ID_HERE"))
CONCURRENCY = int(_get("CONCURRENCY", os.getenv("CONCURRENCY", "5")))
MAX_RETRIES = int(_get("MAX_RETRIES", os.getenv("MAX_RETRIES", "5")))
INITIAL_BACKOFF = float(_get("INITIAL_BACKOFF", os.getenv("INITIAL_BACKOFF", "1.0")))

# REDIS
REDIS_LOCK_TTL = int(_get("CLICKUP_EXPORT_LOCK_TTL", 60 * 30))

# Auth
API_AUTH_TOKEN = _get("API_AUTH_TOKEN", os.getenv("API_AUTH_TOKEN"))

# Exports
KEEP_LAST_N_EXPORTS = int(_get("KEEP_LAST_N_EXPORTS", 7))
