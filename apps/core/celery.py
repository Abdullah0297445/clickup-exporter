import os
from celery.schedules import crontab
from celery import Celery

# Set the default Django settings module for the 'celery' program.
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings.dev")

app = Celery("Clickup Exporter")

# Using a string here means the worker doesn't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object("django.conf:settings", namespace="CELERY")

# Load task modules from all registered Django apps.
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "fetch_clickup_data_and_persist": {
        "task": "export.tasks.fetch_clickup_data_and_persist",
        "schedule": crontab(minute=0, hour=0),
    },
}
