from django.utils import timezone


def get_current_cache_version():
    return timezone.now().strftime("%Y%m%d")


def get_old_cache_version(**timedelta_kwargs):
    if not timedelta_kwargs:
        timedelta_kwargs = {"days": 30}

    return (timezone.now() - timezone.timedelta(**timedelta_kwargs)).strftime("%Y%m%d")
