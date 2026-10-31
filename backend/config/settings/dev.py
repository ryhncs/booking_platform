from .base import *  # noqa: F401,F403

DEBUG = True

# Emails are printed to the console (visible in `docker compose logs worker`).
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
