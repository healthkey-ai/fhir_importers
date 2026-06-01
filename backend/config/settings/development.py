from .base import *  # noqa: F401, F403

DEBUG = True
ALLOWED_HOSTS = ["*"]
CORS_ALLOW_ALL_ORIGINS = True

# Verify-only Firebase mode (FIREBASE_PROJECT_ID set, no service-account key)
# can't perform revocation checks — those need real creds. Skip them in dev so
# a forwarded host ID token verifies on signature + claims alone.
FIREBASE_SKIP_REVOCATION_CHECK = True
