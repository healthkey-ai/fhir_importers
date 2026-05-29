import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import from_url as redis_from_url

from .client import EpicClient
from .config import Settings
from .organizations import OrganizationRegistry
from .routers import router as epic_router
from .service import EpicAuthService
from .state_store import RedisStateStore


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


settings = Settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    organizations = OrganizationRegistry.from_file(settings.organizations_file)
    http_client = httpx.AsyncClient(timeout=settings.http_timeout_seconds)
    redis_client = redis_from_url(settings.redis_url, decode_responses=True)
    state_store = RedisStateStore(redis_client, ttl_seconds=settings.state_ttl_seconds)
    epic_client = EpicClient(http=http_client)
    service = EpicAuthService(
        settings=settings,
        client=epic_client,
        state_store=state_store,
        organizations=organizations,
    )

    app.state.settings = settings
    app.state.organizations = organizations
    app.state.epic_auth_service = service

    try:
        yield
    finally:
        await http_client.aclose()
        await redis_client.aclose()


app = FastAPI(title="MyChart Integration Service", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
app.include_router(epic_router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
