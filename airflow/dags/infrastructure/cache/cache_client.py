import abc
from typing import Any


class CacheClient(abc.ABC):
    @abc.abstractmethod
    def get(self, key: str) -> str | None:
        raise NotImplementedError

    @abc.abstractmethod
    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def delete(self, key: str) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def exists(self, key: str) -> bool:
        raise NotImplementedError
