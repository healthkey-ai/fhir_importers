import pytest
import pytest_asyncio
from cryptography.fernet import Fernet
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.auth import get_current_user_uid
from app.config import Settings
from app.crypto import TokenCipher
from app.organizations import Organization, OrganizationRegistry
from app.routers import get_connections_repo, router as epic_router
from app.service import EpicAuthService

from .fakes import (
    FakeEpicClient,
    InMemoryConnectionsRepository,
    InMemoryStateStore,
    StaticTokenVerifier,
)


@pytest.fixture
def organizations() -> OrganizationRegistry:
    return OrganizationRegistry(
        [
            Organization(
                alias="my_chart_central",
                title="MyChart Central (staging sandbox)",
                endpoint_url="https://fhir.example/sandbox",
            ),
            Organization(
                alias="example_hospital",
                title="Example Hospital",
                endpoint_url="https://fhir.example/prod",
            ),
        ]
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(
        staging_client_id="staging-cid",
        staging_redirect_uri="http://localhost/callback",
        staging_private_key_path="",
        staging_jwks_kid="staging-kid",
        staging_scopes="openid",
        prod_client_id="prod-cid",
        prod_redirect_uri="http://localhost/callback",
        prod_private_key_path="",
        prod_jwks_kid="prod-kid",
        prod_scopes="openid offline_access patient/*.read",
    )


@pytest.fixture
def state_store() -> InMemoryStateStore:
    return InMemoryStateStore()


@pytest.fixture
def epic_client() -> FakeEpicClient:
    return FakeEpicClient()


@pytest.fixture
def cipher() -> TokenCipher:
    return TokenCipher(Fernet.generate_key().decode())


@pytest.fixture
def connections_repo() -> InMemoryConnectionsRepository:
    return InMemoryConnectionsRepository()


@pytest.fixture
def token_verifier() -> StaticTokenVerifier:
    return StaticTokenVerifier(valid_token="test-token", uid="test-uid")


@pytest.fixture
def service(settings, epic_client, state_store, organizations) -> EpicAuthService:
    # `assertion_builder` is injected so tests don't need a real PEM on disk.
    return EpicAuthService(
        settings=settings,
        client=epic_client,
        state_store=state_store,
        organizations=organizations,
        assertion_builder=lambda **kwargs: "test-client-assertion",
    )


@pytest.fixture
def app(
    service,
    organizations,
    connections_repo,
    cipher,
    token_verifier,
) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(epic_router)

    @test_app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    test_app.state.epic_auth_service = service
    test_app.state.organizations = organizations
    test_app.state.token_cipher = cipher
    test_app.state.token_verifier = token_verifier

    async def _override_repo():
        yield connections_repo

    test_app.dependency_overrides[get_connections_repo] = _override_repo
    return test_app


@pytest_asyncio.fixture
async def http_client(app) -> AsyncClient:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac


@pytest.fixture
def bearer() -> dict[str, str]:
    return {"Authorization": "Bearer test-token"}
