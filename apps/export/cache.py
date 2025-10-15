from django.utils import timezone


def get_current_cache_version():
    return timezone.now().strftime("%Y%m%d")
