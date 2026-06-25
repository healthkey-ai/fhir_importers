import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

from services.healthex_client import HealthExClient
from services.healthex_session import HealthExSession

# .env is loaded exactly once at module import; callers (FastAPI lifespan,
# CLI commands, smoke scripts) never call load_dotenv themselves and never
# read os.environ for HealthEx config directly. Idempotent — Pydantic
# Settings may also load .env via its own model_config; both finding the
# same values is harmless.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class ServiceLocator:
    """Construct shared services with their env-var dependencies in one place.

    Every env-var key for any service lives in this file and nowhere else.
    Mirrors the cancerbot-etl ServiceLocator pattern (a shared async http
    client is owned externally and passed in via the constructor, the same
    way that one took a SQLAlchemy engine).
    """

    def __init__(self, *, http: httpx.AsyncClient | None = None) -> None:
        # Async http is owned by FastAPI's lifespan and shared across all
        # async outbound calls; the CLI doesn't need it.
        self._http = http

    @staticmethod
    def get_healthex_session() -> HealthExSession:
        """Sync HealthEx client for CLI / one-shot scripts."""
        return HealthExSession(
            base_url=_healthex_base_url(),
            project_id=_require("HEALTHEX_PROJECT_ID"),
            api_key=_require("HEALTHEX_API_KEY"),
            api_secret=_require("HEALTHEX_API_SECRET"),
        )

    def get_healthex_client(self) -> HealthExClient:
        """Async HealthEx client for FastAPI; uses the injected shared async http."""
        if self._http is None:
            raise RuntimeError(
                "ServiceLocator(http=...) is required for the async HealthExClient; "
                "the CLI's sync path uses get_healthex_session() instead."
            )
        return HealthExClient(
            http=self._http,
            base_url=_healthex_base_url(),
            api_key=_require("HEALTHEX_API_KEY"),
            api_secret=_require("HEALTHEX_API_SECRET"),
        )


def _healthex_base_url() -> str:
    return os.environ.get("HEALTHEX_BASE_URL", "https://api.healthex.io")


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(
            f"{name} not set — add it to .env or export it in your shell"
        )
    return val
