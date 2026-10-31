import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("booking_platform")
# Settings prefixed CELERY_ in Django settings configure the app.
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
