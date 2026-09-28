"""Notifications: create, list (paginated), mark read/unread, unread count."""

from __future__ import annotations

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.db.models import Notification

NOTIF_NEW_DRIVE = "new_drive"
NOTIF_APPLICATION = "application"
NOTIF_STATUS_CHANGE = "status_change"
NOTIF_GENERAL = "general"


def create(
    db: Session,
    *,
    user_id: str,
    institution_id: str,
    type: str,
    title: str,
    body: str,
    link: str | None = None,
    payload: dict | None = None,
    commit: bool = False,
) -> Notification:
    row = Notification(
        user_id=user_id,
        institution_id=institution_id,
        type=type,
        title=title,
        body=body,
        link=link,
        payload=payload or {},
    )
    db.add(row)
    if commit:
        db.commit()
        db.refresh(row)
    return row


def list_for_user(
    db: Session, *, user_id: str, institution_id: str, page: int, limit: int, unread_only: bool = False
) -> tuple[list[Notification], int, int]:
    q = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.institution_id == institution_id,
    )
    unread = (
        db.query(func.count(Notification.id))
        .filter(
            Notification.user_id == user_id,
            Notification.institution_id == institution_id,
            Notification.is_read.is_(False),
        )
        .scalar()
        or 0
    )
    if unread_only:
        q = q.filter(Notification.is_read.is_(False))
    total = q.count()
    rows = (
        q.order_by(Notification.created_at.desc())
        .offset((page - 1) * limit)
        .limit(limit)
        .all()
    )
    return rows, total, unread


def mark_read(db: Session, *, user_id: str, institution_id: str, ids: list[str] | None) -> int:
    from typing import Any, cast

    from sqlalchemy.engine import CursorResult

    q = update(Notification).where(
        Notification.user_id == user_id,
        Notification.institution_id == institution_id,
        Notification.is_read.is_(False),
    )
    if ids:
        q = q.where(Notification.id.in_(ids))
    result = cast(CursorResult[Any], db.execute(q.values(is_read=True, read_at=func.now())))
    return result.rowcount or 0


def notification_count(db: Session, *, user_id: str, institution_id: str) -> int:
    return (
        db.query(func.count(Notification.id))
        .filter(Notification.user_id == user_id, Notification.institution_id == institution_id)
        .scalar()
        or 0
    )


def unsubscribe_target(user_id: str) -> None:
    """Future hook for per-student notification preferences."""
    _ = user_id