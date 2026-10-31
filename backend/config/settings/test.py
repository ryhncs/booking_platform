from .dev import *  # noqa: F401,F403

# Run tasks inline so tests can assert on their effects, and surface their errors.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Own Redis database so tests never touch the dev cache (db 1) or the broker (db 0).
CACHES["default"]["LOCATION"] = f"{REDIS_URL}/2"  # noqa: F405
