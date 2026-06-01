import abc

from cryptography.fernet import Fernet


class BaseTokenCipher(abc.ABC):
    """Symmetric round-trip encrypter for at-rest token storage."""

    @abc.abstractmethod
    def encrypt(self, value: str) -> str: ...

    @abc.abstractmethod
    def decrypt(self, value: str) -> str: ...


class TokenCipher(BaseTokenCipher):
    """Fernet-backed implementation. The key is the standard 32-byte URL-safe base64."""

    def __init__(self, key: str):
        self._fernet = Fernet(key.encode())

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        return self._fernet.decrypt(value.encode()).decode()
