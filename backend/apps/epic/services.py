"""Process-wide singletons wiring the Epic connector together.

In the FastAPI version these were built once in the lifespan context. Here we
build them lazily and cache them: the organization registry and Redis/httpx
clients are reused across requests; httpx.Client and redis.Redis are both safe
for concurrent use.
"""
from functools import lru_cache

import httpx
import redis
from django.conf import settings

from .client import EpicClient
from .organizations import OrganizationRegistry
from .service import EpicAuthService
from .state_store import RedisStateStore


@lru_cache(maxsize=1)
def get_organizations() -> OrganizationRegistry:
    return OrganizationRegistry.from_file(settings.EPIC_ORGANIZATIONS_FILE)


@lru_cache(maxsize=1)
def _http_client() -> httpx.Client:
    return httpx.Client(timeout=settings.EPIC_HTTP_TIMEOUT_SECONDS)


@lru_cache(maxsize=1)
def _redis_client() -> "redis.Redis":
    return redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)


@lru_cache(maxsize=1)
def get_auth_service() -> EpicAuthService:
    return EpicAuthService(
        client=EpicClient(http=_http_client()),
        state_store=RedisStateStore(_redis_client(), ttl_seconds=settings.EPIC_STATE_TTL_SECONDS),
        organizations=get_organizations(),
    )
