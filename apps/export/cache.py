from django.utils import timezone
from datetime import timedelta


def get_current_cache_version():
    return timezone.now().strftime("%Y%m%d")


def get_old_cache_version(**timedelta_kwargs):
    if not timedelta_kwargs:
        timedelta_kwargs = {"days": 30}

    dt = timezone.now() - timedelta(**timedelta_kwargs)
    return dt.strftime("%Y%m%d")
