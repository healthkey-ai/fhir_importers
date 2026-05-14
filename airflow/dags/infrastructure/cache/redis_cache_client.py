import logging

import redis

from infrastructure.cache.cache_client import CacheClient

_logger = logging.getLogger(__name__)


class RedisCacheClient(CacheClient):
    def __init__(self, redis_url: str):
        self._client = redis.Redis.from_url(redis_url)

    def get(self, key: str) -> str | None:
        value = self._client.get(key)
        if value is None:
            return None
        return value.decode("utf-8")

    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        self._client.set(key, value, ex=ttl_seconds)

    def delete(self, key: str) -> None:
        self._client.delete(key)

    def exists(self, key: str) -> bool:
        return bool(self._client.exists(key))
