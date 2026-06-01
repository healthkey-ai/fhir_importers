"""
Test settings — inherits from base, not development.

- DEBUG off (catches template/static errors)
- ALLOWED_HOSTS locked down
- Celery eager (tests are synchronous)
- Firebase revocation check skipped
"""
from .base import *  # noqa: F401, F403

DEBUG = False
ALLOWED_HOSTS = ["localhost", "testserver"]

TASK_BACKEND = "eager"
CELERY_TASK_ALWAYS_EAGER = True

FIREBASE_SKIP_REVOCATION_CHECK = True
