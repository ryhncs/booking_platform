from django.conf import settings

from config import celery_app


def test_celery_uses_redis_broker_from_django_settings():
    assert celery_app.conf.broker_url == settings.CELERY_BROKER_URL
    assert settings.CELERY_BROKER_URL.startswith("redis://")
    assert settings.CELERY_BROKER_URL.endswith("/0")


def test_tests_run_tasks_eagerly():
    assert celery_app.conf.task_always_eager is True


def test_dev_emails_go_to_the_console():
    # Under the test runner Django swaps in locmem; the configured value is what dev uses.
    from config.settings import dev

    assert dev.EMAIL_BACKEND.endswith("console.EmailBackend")
