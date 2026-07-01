from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.airflow import AirflowDagRunState, AirflowError, BaseAirflowClient
from app.auth import BaseTokenVerifier
from app.client import BaseEpicClient, EpicTokens, SmartConfiguration
from app.connections import BaseConnectionsRepository, ConnectionMetadata
from app.healthex_links import BaseHealthExLinksRepository, HealthExLinkMetadata
from app.state_store import BaseStateStore, PendingState


class InMemoryStateStore(BaseStateStore):
    def __init__(self) -> None:
        self._items: dict[str, PendingState] = {}

    async def put(self, state: str, value: PendingState) -> None:
        self._items[state] = value

    async def pop(self, state: str) -> PendingState | None:
        return self._items.pop(state, None)


@dataclass
class _StoredTokens:
    access_token: str
    refresh_token: str | None
    id_token: str | None


class InMemoryConnectionsRepository(BaseConnectionsRepository):
    def __init__(self) -> None:
        self._meta: dict[tuple[str, str], ConnectionMetadata] = {}
        self._tokens: dict[tuple[str, str], _StoredTokens] = {}
        self._created: dict[tuple[str, str], datetime] = {}

    async def upsert(
        self,
        *,
        user_uid: str,
        organization_alias: str,
        access_token: str,
        refresh_token: str | None,
        id_token: str | None,
        scope: str | None,
        patient: str | None,
        expires_at: datetime,
    ) -> ConnectionMetadata:
        key = (user_uid, organization_alias)
        now = datetime.now(timezone.utc)
        self._created.setdefault(key, now)
        self._tokens[key] = _StoredTokens(access_token, refresh_token, id_token)
        prior = self._meta.get(key)
        meta = ConnectionMetadata(
            organization_alias=organization_alias,
            patient=patient,
            scope=scope,
            expires_at=expires_at,
            connected_at=self._created[key],
            last_synced_at=prior.last_synced_at if prior else None,
        )
        self._meta[key] = meta
        return meta

    async def delete(self, user_uid: str, organization_alias: str) -> bool:
        key = (user_uid, organization_alias)
        if key not in self._meta:
            return False
        del self._meta[key]
        self._tokens.pop(key, None)
        self._created.pop(key, None)
        return True

    async def list_for_user(self, user_uid: str) -> list[ConnectionMetadata]:
        return [v for k, v in self._meta.items() if k[0] == user_uid]


class FakeEpicClient(BaseEpicClient):
    def __init__(self) -> None:
        self.smart_configurations: dict[str, SmartConfiguration] = {}
        self.token_response: EpicTokens | None = None
        self.exchange_calls: list[dict] = []
        self.smart_calls: list[tuple[str, str]] = []

    def set_smart_configuration(self, base_url: str, value: SmartConfiguration) -> None:
        self.smart_configurations[base_url] = value

    def set_token_response(self, value: EpicTokens) -> None:
        self.token_response = value

    async def get_smart_configuration(self, base_url: str, client_id: str) -> SmartConfiguration:
        self.smart_calls.append((base_url, client_id))
        if base_url not in self.smart_configurations:
            raise AssertionError(f"FakeEpicClient: no smart-configuration set for {base_url}")
        return self.smart_configurations[base_url]

    async def exchange_authorization_code(
        self,
        token_endpoint: str,
        code: str,
        redirect_uri: str,
        client_id: str,
        code_verifier: str,
        client_assertion: str,
    ) -> EpicTokens:
        self.exchange_calls.append(
            {
                "token_endpoint": token_endpoint,
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "code_verifier": code_verifier,
                "client_assertion": client_assertion,
            }
        )
        if self.token_response is None:
            raise AssertionError("FakeEpicClient: no token_response set")
        return self.token_response


class StaticTokenVerifier(BaseTokenVerifier):
    def __init__(self, valid_token: str = "test-token", uid: str = "test-uid") -> None:
        self._valid = valid_token
        self._uid = uid

    async def verify(self, token: str) -> str:
        if token != self._valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
            )
        return self._uid


class InMemoryHealthExLinksRepository(BaseHealthExLinksRepository):
    """In-memory implementation of BaseHealthExLinksRepository for tests.

    Behaviour mirrors the SQLModel-backed repo — same field semantics,
    same None-return conventions — so anything that passes here should
    behave identically against Postgres. Tests should exercise this fake
    through the abstract base type, not the concrete class, so a future
    signature drift on the base breaks the tests loudly (mypy / attribute
    error) rather than silently.
    """

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], HealthExLinkMetadata] = {}

    async def upsert(
        self,
        *,
        user_uid: str,
        project_id: str,
        external_id: str,
        healthex_patient_id: str | None,
        status: str,
        onboarding_url: str | None,
    ) -> HealthExLinkMetadata:
        key = (user_uid, project_id)
        now = datetime.now(timezone.utc)
        prior = self._store.get(key)
        meta = HealthExLinkMetadata(
            project_id=project_id,
            external_id=external_id,
            healthex_patient_id=healthex_patient_id,
            status=status,
            onboarding_url=onboarding_url,
            consented_at=prior.consented_at if prior else None,
            last_status_polled_at=prior.last_status_polled_at if prior else None,
            last_synced_at=prior.last_synced_at if prior else None,
            connected_at=prior.connected_at if prior else now,
        )
        self._store[key] = meta
        return meta

    async def get(
        self, user_uid: str, project_id: str,
    ) -> HealthExLinkMetadata | None:
        return self._store.get((user_uid, project_id))

    async def list_for_user(self, user_uid: str) -> list[HealthExLinkMetadata]:
        return [v for k, v in self._store.items() if k[0] == user_uid]

    async def delete(self, user_uid: str, project_id: str) -> bool:
        key = (user_uid, project_id)
        if key not in self._store:
            return False
        del self._store[key]
        return True

    async def update_status(
        self,
        *,
        user_uid: str,
        project_id: str,
        status: str,
        healthex_patient_id: str | None = None,
        polled_at: datetime | None = None,
        consented_at: datetime | None = None,
        synced_at: datetime | None = None,
    ) -> HealthExLinkMetadata | None:
        key = (user_uid, project_id)
        prior = self._store.get(key)
        if prior is None:
            return None
        updated = HealthExLinkMetadata(
            project_id=prior.project_id,
            external_id=prior.external_id,
            healthex_patient_id=(
                healthex_patient_id if healthex_patient_id is not None
                else prior.healthex_patient_id
            ),
            status=status,
            onboarding_url=prior.onboarding_url,
            consented_at=(
                consented_at if consented_at is not None and prior.consented_at is None
                else prior.consented_at
            ),
            last_status_polled_at=(
                polled_at if polled_at is not None else prior.last_status_polled_at
            ),
            last_synced_at=(
                synced_at if synced_at is not None else prior.last_synced_at
            ),
            connected_at=prior.connected_at,
        )
        self._store[key] = updated
        return updated


class FakeAirflowClient(BaseAirflowClient):
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.next_dag_run_id: str = "fake-run-1"
        self.fail_next: bool = False

    async def create_dag_run(self, dag: str, dag_run_prefix: str, conf: dict | None) -> str:
        self.calls.append({"dag": dag, "prefix": dag_run_prefix, "conf": conf or {}})
        if self.fail_next:
            self.fail_next = False
            raise AirflowError("forced failure", url="http://test/airflow", method="post")
        return self.next_dag_run_id

    async def get_dag_run_state(self, dag: str, dag_run_id: str) -> AirflowDagRunState:
        return AirflowDagRunState.RUNNING
