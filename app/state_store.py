import json
from dataclasses import asdict, dataclass

from redis.asyncio import Redis


@dataclass
class PendingState:
    code_verifier: str
    token_endpoint: str
    organization_alias: str


class RedisStateStore:
    def __init__(self, client: Redis, ttl_seconds: int):
        self._client = client
        self._ttl = ttl_seconds

    @staticmethod
    def _key(state: str) -> str:
        return f"epic_auth:state:{state}"

    async def put(self, state: str, value: PendingState) -> None:
        await self._client.set(
            self._key(state),
            json.dumps(asdict(value)),
            ex=self._ttl,
        )

    async def pop(self, state: str) -> PendingState | None:
        # Atomic GET+DELETE so a given state can be consumed exactly once.
        key = self._key(state)
        async with self._client.pipeline(transaction=True) as pipe:
            pipe.get(key)
            pipe.delete(key)
            raw, _ = await pipe.execute()
        if raw is None:
            return None
        return PendingState(**json.loads(raw))
