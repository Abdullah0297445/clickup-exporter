import time
from django.utils import timezone

from celery import signals
from celery.utils.log import get_task_logger


logger = get_task_logger(__name__)

start_times = {}

@signals.task_prerun.connect
def start_timer(sender=None, task_id=None, **kwargs):
    start_times[task_id] = time.monotonic()
    start_time = timezone.localtime()
    task_name = f"'{sender.name}' " if sender else ""
    logger.info(f"Starting task {task_name}at {start_time}")


@signals.task_postrun.connect
def stop_timer(sender=None, task_id=None, **kwargs):
    duration = time.monotonic() - start_times.pop(task_id, 0)
    task_name = f"'{sender.name}' " if sender else ""
    logger.info(f"Task {task_name}finished. Elapsed duration: {duration/60.0:.2f} minutes")
