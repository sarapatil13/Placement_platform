"""Encryption helpers for sensitive columns at rest.

`EncryptedString` stores a Fernet ciphertext in a plain VARCHAR column, so
encryption can be enabled by supplying a key without a schema migration. If no
key is configured the field degrades to plaintext and `encryption_enabled()`
reports False, which the health endpoint surfaces as a production warning.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from sqlalchemy import String, TypeDecorator

from app.core.config import settings


def _derive_key(secret: str) -> bytes:
    """Derive a 32-byte urlsafe-base64 key from arbitrary secret material."""
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())


def encryption_enabled() -> bool:
    return bool(settings.field_encryption_key)


def encrypt(plaintext: str) -> str:
    if plaintext is None:
        return None  # type: ignore[return-value]
    if not encryption_enabled():
        return plaintext
    from cryptography.fernet import Fernet

    token = Fernet(_derive_key(settings.field_encryption_key))
    return token.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt(ciphertext: str) -> str:
    if ciphertext is None:
        return None  # type: ignore[return-value]
    if not encryption_enabled():
        return ciphertext
    from cryptography.fernet import Fernet, InvalidToken

    token = Fernet(_derive_key(settings.field_encryption_key))
    try:
        return token.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        # Raised when the key changed after data was written. Never leak plaintext.
        raise ValueError("Unable to decrypt value with the configured key.") from exc


class EncryptedString(TypeDecorator):
    """Transparently encrypts/decrypts a string column."""

    impl = String
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return encrypt(str(value))

    def process_result_value(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        return decrypt(str(value))
