"""Ephemeral PKCE state, stored in Redis (synchronous client).

Ported from the async FastAPI version to a blocking redis client so it fits
Django/DRF's synchronous request cycle. State is consumed exactly once via an
atomic GET+DELETE pipeline.
"""
import json
from dataclasses import asdict, dataclass

import redis


@dataclass
class PendingState:
    code_verifier: str
    token_endpoint: str
    organization_alias: str


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
