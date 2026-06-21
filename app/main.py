import logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from redis.asyncio import from_url as redis_from_url

from .airflow import AirflowClient
from .auth import FirebaseTokenVerifier
from .client import EpicClient
from .config import Settings
from .crypto import TokenCipher
from .db import create_engine, create_sessionmaker
from .healthex_client import HealthExClient
from .healthex_routers import router as healthex_router
from .organizations import OrganizationRegistry
from .routers import router as epic_router
from .service import EpicAuthService
from .state_store import RedisStateStore

# ES modules need a JS content-type; Python's mimetypes doesn't always ship .mjs.
mimetypes.add_type("application/javascript", ".mjs")


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

    # Schema is managed by Alembic; the container entrypoint runs
    # `alembic upgrade head` before uvicorn starts.
    engine = create_engine(settings.database_url)

    app.state.settings = settings
    app.state.organizations = organizations
    app.state.epic_auth_service = service
    app.state.db_sessionmaker = create_sessionmaker(engine)
    app.state.token_cipher = TokenCipher(settings.token_encryption_key)
    app.state.token_verifier = FirebaseTokenVerifier()
    app.state.airflow_client = AirflowClient(
        http=http_client,
        base_url=settings.airflow_url,
        username=settings.airflow_username,
        password=settings.airflow_password,
    )
    app.state.healthex_client = HealthExClient(
        http=http_client,
        base_url=settings.healthex_base_url,
        api_key=settings.healthex_api_key,
        api_secret=settings.healthex_api_secret,
    )

    try:
        yield
    finally:
        await http_client.aclose()
        await redis_client.aclose()
        await engine.dispose()


app = FastAPI(title="MyChart Integration Service", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
app.include_router(epic_router)
app.include_router(healthex_router)


# Serve the federation remote bundle (remoteEntry.js + chunks) at /remote so the
# host loads it from `<service-url>/remote/remoteEntry.js`. CORSMiddleware above
# applies to this mount too. If the directory is missing (e.g. uvicorn run
# outside the image without `npm run build:remote`), skip mounting.
_remote_dir = Path(settings.remote_bundle_dir)
if _remote_dir.is_dir():
    app.mount("/remote", StaticFiles(directory=str(_remote_dir)), name="remote")
else:
    logging.getLogger(__name__).info(
        "remote_bundle_dir %s does not exist; /remote mount skipped", _remote_dir
    )


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
