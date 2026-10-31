from django.apps import AppConfig


class BookingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.bookings"

    def ready(self) -> None:
        from . import signals  # noqa: F401  (registers receivers)
