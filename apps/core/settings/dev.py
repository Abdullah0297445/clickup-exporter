import os
from .default import * # noqa

SECRET_KEY = os.getenv("SECRET_KEY")

DEBUG = bool(int(os.getenv("DEBUG", 0)))

ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    # Local apps
    "core",
    "export"
]

MIDDLEWARE = [
    "core.middlewares.healthcheck.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.gzip.GZipMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

AUTH_PASSWORD_VALIDATORS = []
DATABASES = {}
TEMPLATES[0]["OPTIONS"]["context_processors"] = []
TEMPLATES[0]["APP_DIRS"] = False

CSRF_TRUSTED_ORIGINS = [
    "https://*.carteblanche.tech",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
CSRF_TRUSTED_ORIGINS += list(
    filter(None, os.environ.get("CSRF_TRUSTED_ORIGINS", "").split(","))
)

CELERY_TASKS_ACK_LATE = True
BROKER_SCHEME = "rediss://" if bool(int(os.getenv("BROKER_SSL", 0))) else "redis://"
BROKER_QS = "?ssl_cert_reqs=required" if bool(int(os.getenv("BROKER_SSL", 0))) else ""
CELERY_BROKER_READ_URL = f"{BROKER_SCHEME}{os.getenv('BROKER_READ_HOST')}:{os.getenv('BROKER_PORT', 6379)}{BROKER_QS}"
CELERY_BROKER_WRITE_URL = f"{BROKER_SCHEME}{os.getenv('BROKER_WRITE_HOST')}:{os.getenv('BROKER_PORT', 6379)}{BROKER_QS}"
CELERY_BROKER_USE_SSL = bool(int(os.getenv("BROKER_SSL", 0)))
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_BROKER_TRANSPORT_OPTIONS = {"visibility_timeout": 600}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": CELERY_BROKER_WRITE_URL,
        "TIMEOUT": None,
    }
}
