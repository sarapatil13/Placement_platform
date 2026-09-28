"""Audit-trail service.

Every call appends to `audit_logs`. Records are never updated or deleted.
Callers pass the current request context (actor, IP, user-agent) resolved by
`app.api.deps`; batch/background writes pass `actor_id=None`.
"""

from __future__ import annotations

import ipaddress
from typing import Any

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models import AuditLog

logger = get_logger("audit")


def _sanitise_ip(ip: str | None) -> str | None:
    if not ip:
        return None
    if ip in {"127.0.0.1", "::1", "0.0.0.0", "unknown"}:
        return ip
    try:
        addr = ipaddress.ip_address(ip)
        if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
            return str(addr.ipv4_mapped)
        return ip
    except (ValueError, TypeError):
        return None


class AuditContext:
    """Immutable request context passed between layers for audit persistence."""

    __slots__ = ("actor_id", "actor_email", "actor_role", "ip_address", "user_agent", "institution_id")

    def __init__(
        self,
        *,
        actor_id: str | None,
        actor_email: str | None,
        actor_role: str | None,
        ip_address: str | None,
        user_agent: str | None,
        institution_id: str | None,
    ) -> None:
        self.actor_id = actor_id
        self.actor_email = actor_email
        self.actor_role = actor_role
        self.ip_address = ip_address
        self.user_agent = user_agent
        self.institution_id = institution_id


def record(
    db: Session,
    *,
    action: str,
    context: AuditContext | None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    outcome: str = "success",
    detail: dict[str, Any] | None = None,
    institution_id: str | None = None,
) -> AuditLog:
    row = AuditLog(
        institution_id=institution_id
        or (context.institution_id if context else None),
        actor_id=context.actor_id if context else None,
        actor_email=context.actor_email if context else None,
        actor_role=context.actor_role if context else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        outcome=outcome,
        ip_address=_sanitise_ip(context.ip_address if context else None),
        user_agent=(context.user_agent[:300] if context and context.user_agent else None),
        detail=detail or {},
    )
    db.add(row)
    db.flush()
    return row


def flush_failed_login(db: Session, *, actor_email: str, ip: str | None) -> None:
    """Log a failed authentication attempt. actor_id is unknown at this point."""
    record(
        db,
        action="auth.login.failed",
        context=AuditContext(
            actor_id=None,
            actor_email=actor_email,
            actor_role=None,
            ip_address=ip,
            user_agent=None,
            institution_id=None,
        ),
        outcome="failure",
        entity_type="user",
    )