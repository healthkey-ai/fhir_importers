from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    client_id: str
    redirect_uri: str
    private_key_path: str
    jwks_kid: str

    scopes: str = "openid offline_access patient/*.read"
    organizations_file: str = "organizations.json"
    redis_url: str = "redis://localhost:6379/0"
    state_ttl_seconds: int = 600
    http_timeout_seconds: float = 15.0

    # Comma-separated list of origins allowed to call the API from a browser.
    cors_allowed_origins: str = "http://localhost:5173"
