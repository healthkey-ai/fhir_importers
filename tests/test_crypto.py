import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.crypto import BaseTokenCipher, TokenCipher


def test_token_cipher_is_base_subclass():
    assert issubclass(TokenCipher, BaseTokenCipher)


def test_round_trip_preserves_value():
    cipher = TokenCipher(Fernet.generate_key().decode())
    assert cipher.decrypt(cipher.encrypt("hello-world")) == "hello-world"


def test_ciphertext_differs_from_plaintext():
    cipher = TokenCipher(Fernet.generate_key().decode())
    assert cipher.encrypt("hello-world") != "hello-world"


def test_decrypt_with_other_key_fails():
    a = TokenCipher(Fernet.generate_key().decode())
    b = TokenCipher(Fernet.generate_key().decode())
    encrypted = a.encrypt("secret")
    with pytest.raises(InvalidToken):
        b.decrypt(encrypted)
