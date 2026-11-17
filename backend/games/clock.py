from django.utils import timezone


def now():
    """The application's trusted time. Tests replace it instead of waiting."""
    return timezone.now()
