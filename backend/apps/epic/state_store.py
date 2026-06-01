"""Ephemeral PKCE state for an in-flight Epic authorization.

Two interchangeable backends implement the same put/pop contract (consume
exactly once): `DbStateStore` (default — survives across stateless Cloud Run
instances) and `RedisStateStore` (the original, behind EPIC_STATE_BACKEND=redis).
"""
import json
from dataclasses import asdict, dataclass
from datetime import timedelta
from typing import Protocol

import redis
from django.db import transaction
from django.utils import timezone


@dataclass
class PendingState:
    code_verifier: str
    token_endpoint: str
    organization_alias: str


class StateStore(Protocol):
    def put(self, state: str, value: PendingState) -> None: ...
    def pop(self, state: str) -> PendingState | None: ...


class DbStateStore:
    """Postgres-backed state — no shared cache needed across Cloud Run instances."""

    def __init__(self, ttl_seconds: int):
        self._ttl = ttl_seconds

    def put(self, state: str, value: PendingState) -> None:
        from .models import EpicAuthState

        now = timezone.now()
        EpicAuthState.objects.update_or_create(
            state=state,
            defaults={
                "code_verifier": value.code_verifier,
                "token_endpoint": value.token_endpoint,
                "organization_alias": value.organization_alias,
                "expires_at": now + timedelta(seconds=self._ttl),
            },
        )
        # Opportunistic GC so abandoned authorizations don't accumulate.
        EpicAuthState.objects.filter(expires_at__lt=now).delete()

    def pop(self, state: str) -> PendingState | None:
        from .models import EpicAuthState

        now = timezone.now()
        # Lock + delete so a given state is consumed exactly once even if the
        # callback is delivered twice concurrently.
        with transaction.atomic():
            row = EpicAuthState.objects.select_for_update().filter(state=state).first()
            if row is None:
                return None
            expired = row.expires_at <= now
            value = PendingState(
                code_verifier=row.code_verifier,
                token_endpoint=row.token_endpoint,
                organization_alias=row.organization_alias,
            )
            row.delete()
        return None if expired else value


class RedisStateStore:
    def __init__(self, client: "redis.Redis", ttl_seconds: int):
        self._client = client
        self._ttl = ttl_seconds

    @staticmethod
    def _key(state: str) -> str:
        return f"epic_auth:state:{state}"

    def put(self, state: str, value: PendingState) -> None:
        self._client.set(self._key(state), json.dumps(asdict(value)), ex=self._ttl)

    def pop(self, state: str) -> PendingState | None:
        # Atomic GET+DELETE so a given state can be consumed exactly once.
        key = self._key(state)
        with self._client.pipeline(transaction=True) as pipe:
            pipe.get(key)
            pipe.delete(key)
            raw, _ = pipe.execute()
        if raw is None:
            return None
        return PendingState(**json.loads(raw))
