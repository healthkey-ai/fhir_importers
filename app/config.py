from dataclasses import dataclass

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
