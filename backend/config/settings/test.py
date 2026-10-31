from .dev import *  # noqa: F401,F403

# Run tasks inline so tests can assert on their effects, and surface their errors.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
