"""
Base Django settings for the HealthKey FHIR connector (fhir_importers).

Ported from the original FastAPI MyChart-integration service. Joins the
HealthKey platform by adopting the shared OIDC (issuer, sub) Identity model
(see ctomop/docs/identity-architecture.md) — same `accounts` app, providers,
and PartnerAuthentication as hk-labs.
"""
from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    CORS_ALLOWED_ORIGINS=(list, []),
    JWT_ACCESS_LIFETIME_MINUTES=(int, 15),
    JWT_REFRESH_LIFETIME_DAYS=(int, 7),
)

env_file = BASE_DIR / ".env"
if env_file.exists():
    environ.Env.read_env(env_file)

SECRET_KEY = env("SECRET_KEY", default="dev-insecure-key-change-in-production")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    # Local apps
    "apps.accounts",
    "apps.epic",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": env.db("DATABASE_URL", default="postgres:///fhir_importers"),
}

AUTH_USER_MODEL = "accounts.Identity"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# ── Logging ─────────────────────────────────────────────────────────────────
LOG_LEVEL = env("LOG_LEVEL", default="INFO")
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "app": {"format": "[{asctime}] {levelname} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "app"},
    },
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
        "apps": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "celery": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "httpx": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "httpcore": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
WHITENOISE_ALLOW_ALL_ORIGINS = True

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ── Pluggable partner auth providers ──────────────────────────────────────
# PartnerAuthentication iterates these in order; the first provider that
# recognises the bearer token wins. Empty list = standalone mode (local
# identities only). Add the Firebase provider for integrated mode (ht-phr).
PARTNER_AUTH_PROVIDERS = env.list(
    "PARTNER_AUTH_PROVIDERS",
    default=["apps.accounts.providers.firebase.FirebaseTokenProvider"],
)

# DRF
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "apps.accounts.partner_auth.PartnerAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_RENDERER_CLASSES": (
        "rest_framework.renderers.JSONRenderer",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env("JWT_ACCESS_LIFETIME_MINUTES")),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env("JWT_REFRESH_LIFETIME_DAYS")),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

CORS_ALLOWED_ORIGINS = env("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True

# ── Celery / Redis ────────────────────────────────────────────────────────
# Phase 0 ships the bootstrap so the worker can boot; sync tasks land in
# Phase 2. Local dev / tests run eager (no broker needed).
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")
_BROKER_URL = env("CELERY_BROKER_URL", default="")
CELERY_BROKER_URL = _BROKER_URL or "memory://"
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default="cache+memory://")
CELERY_TASK_ALWAYS_EAGER = False
import sys  # noqa: E402
if "pytest" in sys.modules or env("TASK_BACKEND", default="celery") == "eager":
    CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
TASK_BACKEND = env("TASK_BACKEND", default="celery")

# ── ctomop integration (sync target — wired in Phase 2) ───────────────────
# Mirrors hk-labs: identity travels in the body (actor_iss/actor_sub) and the
# call is authenticated with CTOMOP_SERVICE_TOKEN (an OAuth2 patient/*.write
# bearer). CTOMOP_SYNC_URL points at ctomop's new POST /api/fhir/sync/.
_ctomop_base = env("CTOMOP_BASE_URL", default="")
CTOMOP_SYNC_URL = env(
    "CTOMOP_SYNC_URL",
    default=f"{_ctomop_base.rstrip('/')}/api/fhir/sync/" if _ctomop_base else "",
)
CTOMOP_SERVICE_TOKEN = env("CTOMOP_SERVICE_TOKEN", default="")
# A first full-patient ingest is synchronous on ctomop and can be slow.
CTOMOP_HTTP_TIMEOUT_SECONDS = env.float("CTOMOP_HTTP_TIMEOUT_SECONDS", default=180.0)

# Fernet key (urlsafe-base64, 32 bytes) for encrypting Epic tokens at rest.
# Empty → dev fallback derived from SECRET_KEY (see apps.epic.crypto). Set a
# real key in production.
TOKEN_ENCRYPTION_KEY = env("TOKEN_ENCRYPTION_KEY", default="")

# ── Epic / MyChart SMART-on-FHIR connector config ─────────────────────────
# Staging = Epic non-production / sandbox app, used ONLY for the sandbox org
# (EPIC_STAGING_ORG_ALIAS). Every other org uses the production credentials.
EPIC_STAGING_ORG_ALIAS = env("EPIC_STAGING_ORG_ALIAS", default="my_chart_central")

EPIC_STAGING_CLIENT_ID = env("EPIC_STAGING_CLIENT_ID", default="")
EPIC_STAGING_REDIRECT_URI = env("EPIC_STAGING_REDIRECT_URI", default="")
EPIC_STAGING_PRIVATE_KEY_PATH = env("EPIC_STAGING_PRIVATE_KEY_PATH", default="")
EPIC_STAGING_JWKS_KID = env("EPIC_STAGING_JWKS_KID", default="")
EPIC_STAGING_SCOPES = env("EPIC_STAGING_SCOPES", default="openid profile fhirUser")

EPIC_PROD_CLIENT_ID = env("EPIC_PROD_CLIENT_ID", default="")
EPIC_PROD_REDIRECT_URI = env("EPIC_PROD_REDIRECT_URI", default="")
EPIC_PROD_PRIVATE_KEY_PATH = env("EPIC_PROD_PRIVATE_KEY_PATH", default="")
EPIC_PROD_JWKS_KID = env("EPIC_PROD_JWKS_KID", default="")
EPIC_PROD_SCOPES = env("EPIC_PROD_SCOPES", default="openid offline_access patient/*.read")

EPIC_ORGANIZATIONS_FILE = env(
    "EPIC_ORGANIZATIONS_FILE",
    default=str(BASE_DIR / "apps" / "epic" / "organizations.json"),
)
EPIC_STATE_TTL_SECONDS = env.int("EPIC_STATE_TTL_SECONDS", default=600)
EPIC_HTTP_TIMEOUT_SECONDS = env.float("EPIC_HTTP_TIMEOUT_SECONDS", default=15.0)

# ── Firebase Admin SDK (integrated mode) ──────────────────────────────────
# Shared credentials with the host app (ht-phr).
FIREBASE_CREDENTIALS_JSON = env("FIREBASE_CREDENTIALS_JSON", default="")
FIREBASE_PROJECT_ID = env("FIREBASE_PROJECT_ID", default="")
FIREBASE_SKIP_REVOCATION_CHECK = env.bool("FIREBASE_SKIP_REVOCATION_CHECK", default=False)
PARTNER_AUTH_CACHE_TTL = env.int("PARTNER_AUTH_CACHE_TTL", default=60)


def _init_firebase_admin():
    import os
    import firebase_admin
    from firebase_admin import credentials as fb_credentials

    if firebase_admin._apps:
        return

    project_id = FIREBASE_PROJECT_ID
    options = {"projectId": project_id} if project_id else {}

    raw_json = FIREBASE_CREDENTIALS_JSON
    if raw_json.strip():
        import json as _json
        cred = fb_credentials.Certificate(_json.loads(raw_json))
    elif os.environ.get("FIREBASE_AUTH_EMULATOR_HOST"):

        class _EmulatorCredential(fb_credentials.Base):
            def get_credential(self):
                return None

        cred = _EmulatorCredential()
    else:
        try:
            cred = fb_credentials.ApplicationDefault()
        except Exception:
            cred = None

    if cred is None:
        if not project_id:
            # Nothing to verify against — leave Firebase uninitialised.
            return

        # Verify-only mode: no service-account key and no ADC, but a project id
        # is configured. Initialise with a no-op credential so the connector can
        # still verify host-issued ID tokens against Google's public certs — no
        # secret needed to *verify* (only to mint/revoke). Revocation checks hit
        # the Firebase backend and need real creds, so they must be disabled in
        # this mode (FIREBASE_SKIP_REVOCATION_CHECK — set in dev settings).
        class _VerifyOnlyCredential(fb_credentials.Base):
            def get_credential(self):
                return None

        cred = _VerifyOnlyCredential()

    try:
        firebase_admin.initialize_app(cred, options)
    except ValueError:
        pass


# Only initialise Firebase when its provider is actually configured. This
# keeps standalone mode (PARTNER_AUTH_PROVIDERS=[]) free of Firebase deps.
if any("firebase" in p.lower() for p in PARTNER_AUTH_PROVIDERS):
    _init_firebase_admin()
