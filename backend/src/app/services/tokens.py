"""Server-side refresh-token revocation (denylist keyed by decoded JTI).

Revocation never changes token lifetimes: the denylist row carries the token's
own ``exp`` and is only looked up for tokens that are still cryptographically
valid. Expired rows are pruned opportunistically whenever a token is revoked.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.security import hash_token
from app.db.models import RevokedRefreshToken


class _AsUTC:
    """Normalise naive SQLite datetimes to aware UTC."""

    @staticmethod
    def conv(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def _prune_expired(db: Session, *, before: datetime | None = None) -> None:
    cutoff = before or datetime.now(UTC)
    db.execute(delete(RevokedRefreshToken).where(RevokedRefreshToken.expires_at < cutoff))


def revoke_refresh_token(
    db: Session,
    *,
    jti: str,
    user_id: str,
    expires_at: datetime,
) -> bool:
    """Denylist a refresh token's JTI. Returns True when newly revoked."""
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        return False  # already dead; nothing to record
    digest = hash_token(jti)
    existing = (
        db.query(RevokedRefreshToken)
        .filter(RevokedRefreshToken.jti_hash == digest)
        .first()
    )
    if existing is not None:
        return False
    db.add(
        RevokedRefreshToken(
            user_id=user_id,
            jti_hash=digest,
            expires_at=expires_at,
        )
    )
    _prune_expired(db, before=datetime.now(UTC))
    db.commit()
    return True


def is_refresh_token_revoked(db: Session, *, jti: str) -> bool:
    """True when the JTI is denylisted and still inside its validity window."""
    digest = hash_token(jti)
    row = (
        db.query(RevokedRefreshToken)
        .filter(RevokedRefreshToken.jti_hash == digest)
        .first()
    )
    if row is None:
        return False
    expires_at = _AsUTC.conv(row.expires_at)
    return expires_at is not None and expires_at > datetime.now(UTC)


__all__ = [
    "revoke_refresh_token",
    "is_refresh_token_revoked",
]