"""Password hashing and JWT issuance/verification.

Uses bcrypt directly (not passlib) to avoid the passlib/bcrypt version
interoperability problems. Hashes are stored in the modular bcrypt format so
`rounds` can be raised later without invalidating existing hashes: verification
reads the cost factor out of the stored hash.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import bcrypt
import jwt

from app.core.config import settings

TokenType = Literal["access", "refresh"]
RoleName = Literal["student", "placement_admin", "super_admin"]

# Roles are ordered by privilege for coarse checks. Resource-level authorization
# is still enforced explicitly via the RBAC matrix in app.core.rbac.
ROLE_STUDENT: RoleName = "student"
ROLE_PLACEMENT_ADMIN: RoleName = "placement_admin"
ROLE_SUPER_ADMIN: RoleName = "super_admin"
ALL_ROLES: tuple[RoleName, ...] = (ROLE_STUDENT, ROLE_PLACEMENT_ADMIN, ROLE_SUPER_ADMIN)
ADMIN_ROLES: frozenset[str] = frozenset({ROLE_PLACEMENT_ADMIN, ROLE_SUPER_ADMIN})


class TokenError(Exception):
    """Raised when a token is invalid, expired, or of the wrong type."""


# --------------------------------------------------------------------------- #
# Password hashing
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    if not isinstance(password, str) or not password:
        raise ValueError("password must be a non-empty string")
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time verification of a password against a stored bcrypt hash."""
    if not password or not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """True when the stored hash uses a lower cost than the current setting."""
    try:
        rounds = int(password_hash.split("$")[2])
    except (IndexError, ValueError):
        return True
    return rounds < settings.bcrypt_rounds


def password_policy_errors(password: str, full_name: str = "", email: str = "") -> list[str]:
    """Return human-readable policy violations. Empty list means the password passes."""
    errors: list[str] = []
    if len(password) < settings.password_min_length:
        errors.append(
            f"Password must be at least {settings.password_min_length} characters long."
        )
    classes = sum(
        [
            any(c.islower() for c in password),
            any(c.isupper() for c in password),
            any(c.isdigit() for c in password),
            any(not c.isalnum() for c in password),
        ]
    )
    if classes < 3:
        errors.append(
            "Password must include at least three of: lowercase, uppercase, digits, symbols."
        )
    lowered = password.lower()
    if full_name and len(full_name) > 2:
        parts = [p for p in full_name.lower().split() if len(p) > 2]
        if any(p in lowered for p in parts):
            errors.append("Password must not contain your name.")
    if email:
        local = email.split("@")[0].lower()
        if len(local) > 3 and local in lowered:
            errors.append("Password must not contain your email address.")
    if lowered in {"password", "password123", "qwerty123", "admin1234", "12345678"}:
        errors.append("Password is too common.")
    return errors


# --------------------------------------------------------------------------- #
# JWT
# --------------------------------------------------------------------------- #
def _now() -> datetime:
    return datetime.now(UTC)


def _base_claims(token_type: TokenType, role: str, institution_id: str | None) -> dict[str, Any]:
    return {
        "sub": str(uuid.uuid4()),
        "typ": token_type,
        "role": role,
        "institution_id": institution_id,
        "iat": int(_now().timestamp()),
        "jti": secrets.token_urlsafe(16),
        "iss": settings.institution.identity_issuer,
    }


def create_access_token(
    *,
    role: str,
    institution_id: str | None,
    expires_minutes: int | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    minutes = expires_minutes or settings.access_token_expire_minutes
    claims = _base_claims("access", role, institution_id)
    claims["exp"] = _now() + timedelta(minutes=minutes)
    if extra_claims:
        claims.update(extra_claims)
    return jwt.encode(claims, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    *,
    role: str,
    institution_id: str | None,
    sub: str | None = None,
) -> str:
    claims = _base_claims("refresh", role, institution_id)
    if sub:
        claims["sub"] = sub
    claims["exp"] = _now() + timedelta(days=settings.refresh_token_expire_days)
    return jwt.encode(claims, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, *, expected_type: TokenType = "access") -> dict[str, Any]:
    """Decode and validate a JWT. Raises TokenError on any problem."""
    if not token or not isinstance(token, str):
        raise TokenError("Token is missing.")
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.institution.identity_issuer,
            options={"require": ["exp", "iat", "sub", "typ"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise TokenError("Token has expired.") from exc
    except jwt.InvalidIssuerError as exc:
        raise TokenError("Token issuer is not recognised.") from exc
    except jwt.InvalidTokenError as exc:
        raise TokenError("Token is invalid.") from exc

    if payload.get("typ") != expected_type:
        raise TokenError(f"Expected a {expected_type} token.")
    return payload


def decode_token_loose(token: str, *, expected_type: TokenType = "refresh") -> dict[str, Any] | None:
    """Decode without validating expiry, for revocation bookkeeping (logout).

    Only the cryptographic signature, issuer, typing, and required claims are
    checked; an expired-but-genuine token still yields its ``jti``/``exp`` so it
    can be recorded as revoked. Returns None for anything malformed or forged.
    """
    if not token or not isinstance(token, str):
        return None
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.institution.identity_issuer,
            options={"require": ["exp", "iat", "sub", "typ"], "verify_exp": False},
        )
    except jwt.InvalidTokenError:
        return None
    if payload.get("typ") != expected_type:
        return None
    return payload


# --------------------------------------------------------------------------- #
# Opaque tokens (share links, email verification)
# --------------------------------------------------------------------------- #
def generate_opaque_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    """Deterministic hash of an opaque token, for storing a lookup digest."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def constant_time_compare(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)
