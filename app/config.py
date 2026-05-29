from dataclasses import dataclass
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

# The one sandbox org that uses Epic's non-production (staging) credentials.
# Every other org uses the production credentials.
STAGING_ORG_ALIAS = "my_chart_central"


@dataclass(frozen=True)
class EpicConfig:
    client_id: str
    redirect_uri: str
    private_key_path: str
    jwks_kid: str
    scopes: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Staging = Epic non-production / sandbox app. Used ONLY for the MyChart
    # sandbox org (STAGING_ORG_ALIAS).
    staging_client_id: str = ""
    staging_redirect_uri: str = ""
    staging_private_key_path: str = ""
    staging_jwks_kid: str = ""
    staging_scopes: str = "openid profile fhirUser"

    # Production = Epic production app. Used for all real organizations.
    prod_client_id: str = ""
    prod_redirect_uri: str = ""
    prod_private_key_path: str = ""
    prod_jwks_kid: str = ""
    prod_scopes: str = "openid offline_access patient/*.read"

    organizations_file: str = "organizations.json"
    redis_url: str = "redis://localhost:6379/0"
    state_ttl_seconds: int = 600
    http_timeout_seconds: float = 15.0

    # Comma-separated origins allowed to call the API from a browser.
    cors_allowed_origins: str = "http://localhost:3001"

    # Postgres (own database for MyChart connections).
    database_url: str = "postgresql+asyncpg://fhir:fhir@localhost:5432/fhir_importers"

    # Firebase ID token verification (mirrors ht-phr). Emulator mode is enabled
    # by the FIREBASE_AUTH_EMULATOR_HOST env var (read by firebase-admin).
    firebase_project_id: str = ""
    firebase_credentials_path: str = ""

    # Fernet key used to encrypt Epic tokens at rest. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    token_encryption_key: str = ""

    # Airflow — triggered after /auth/finish and from the explicit resync endpoint.
    airflow_url: str = ""
    airflow_username: str = ""
    airflow_password: str = ""

    # Directory holding the federation remote bundle (remoteEntry.js + chunks).
    # The image's multi-stage build drops the Vite output here; the app mounts it
    # at /remote via StaticFiles. If the directory is missing (e.g. running
    # uvicorn outside the container without `npm run build:remote`), the mount
    # is skipped — local dev uses `npm run dev:remote` on :5178 instead.
    remote_bundle_dir: str = "/app/frontend_remote"

    def _staging(self) -> EpicConfig:
        return EpicConfig(
            client_id=self.staging_client_id,
            redirect_uri=self.staging_redirect_uri,
            private_key_path=self.staging_private_key_path,
            jwks_kid=self.staging_jwks_kid,
            scopes=self.staging_scopes,
        )

    def _prod(self) -> EpicConfig:
        return EpicConfig(
            client_id=self.prod_client_id,
            redirect_uri=self.prod_redirect_uri,
            private_key_path=self.prod_private_key_path,
            jwks_kid=self.prod_jwks_kid,
            scopes=self.prod_scopes,
        )

    def epic_config_for_org(self, organization_alias: str) -> EpicConfig:
        return self._staging() if organization_alias == STAGING_ORG_ALIAS else self._prod()


@lru_cache
def get_settings() -> Settings:
    return Settings()
