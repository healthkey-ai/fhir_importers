import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from dotenv import load_dotenv

from services.healthex_client import HealthExClient

# .env is loaded exactly once at module import; callers (FastAPI lifespan,
# CLI commands, smoke scripts) never call load_dotenv themselves and never
# read os.environ for HealthEx config directly. Idempotent — Pydantic
# Settings may also load .env via its own model_config; both finding the
# same values is harmless.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")


class ServiceLocator:
    """Construct shared services with their env-var dependencies in one place.

    Every env-var key for any service lives in this file and nowhere else.
    Mirrors the cancerbot-etl ServiceLocator pattern: the long-lived shared
    resource (here an httpx.AsyncClient) is owned externally and passed in
    via the constructor, the same way that one took a SQLAlchemy Engine.
    """

    def __init__(self, *, http: httpx.AsyncClient | None = None) -> None:
        # Async http is owned by FastAPI's lifespan and shared across all
        # async outbound calls. The CLI uses `healthex_client()` below, which
        # owns the lifecycle of its own short-lived AsyncClient.
        self._http = http

    def get_healthex_client(self) -> HealthExClient:
        """Build a HealthExClient over the externally-owned AsyncClient.

        For FastAPI lifespan use — the AsyncClient outlives all requests.
        CLI callers should use `ServiceLocator.healthex_client()` instead.
        """
        if self._http is None:
            raise RuntimeError(
                "ServiceLocator(http=...) is required to build the async "
                "HealthExClient. CLI callers should use the "
                "`healthex_client()` async context manager."
            )
        return HealthExClient(
            http=self._http,
            base_url=_healthex_base_url(),
            project_id=_require("HEALTHEX_PROJECT_ID"),
            api_key=_require("HEALTHEX_API_KEY"),
            api_secret=_require("HEALTHEX_API_SECRET"),
        )

    @staticmethod
    @asynccontextmanager
    async def healthex_client() -> AsyncIterator[HealthExClient]:
        """Yield a HealthExClient over a short-lived AsyncClient (CLI / scripts).

        Owns the AsyncClient's lifecycle — opens, yields, closes. Suitable
        for one-shot CLI commands; FastAPI uses `get_healthex_client()` over
        its lifespan-owned AsyncClient instead.
        """
        async with httpx.AsyncClient(timeout=60.0) as http:
            yield ServiceLocator(http=http).get_healthex_client()


def _healthex_base_url() -> str:
    return os.environ.get("HEALTHEX_BASE_URL", "https://api.healthex.io")


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(
            f"{name} not set — add it to .env or export it in your shell"
        )
    return val
