"""Notifications: create, list (paginated), mark read/unread, unread count."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from app.db.models import Notification

NOTIF_NEW_DRIVE = "new_drive"
NOTIF_APPLICATION = "application"
NOTIF_STATUS_CHANGE = "status_change"
NOTIF_DEADLINE = "deadline_soon"
NOTIF_GENERAL = "general"

DEADLINE_REMINDER_WINDOW = timedelta(hours=48)


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


def ensure_deadline_reminders(db: Session, *, user, student) -> int:
    """Create one "deadline_soon" notification per eligible drive closing within 48h.

    Idempotent: a notification is only created when the user has no existing
    deadline reminder carrying the same ``drive_id`` in its payload, and the
    student has not already applied. Commits only when something is created.
    """
    from app.db.models import (
        DRIVE_PUBLISHED,
        Application,
        PlacementDrive,
    )
    from app.services.eligibility import evaluate

    now = datetime.now(UTC)
    horizon = now + DEADLINE_REMINDER_WINDOW
    drives = (
        db.query(PlacementDrive)
        .filter(
            PlacementDrive.institution_id == student.institution_id,
            PlacementDrive.status == DRIVE_PUBLISHED,
            PlacementDrive.apply_by.isnot(None),
            PlacementDrive.apply_by >= now,
            PlacementDrive.apply_by <= horizon,
        )
        .all()
    )
    if not drives:
        return 0

    drive_ids = [d.id for d in drives]
    applied = {
        row[0]
        for row in db.query(Application.drive_id)
        .filter(Application.student_id == student.id, Application.drive_id.in_(drive_ids))
        .all()
    }
    reminded = {
        (n.payload or {}).get("drive_id")
        for n in db.query(Notification)
        .filter(
            Notification.user_id == user.id,
            Notification.institution_id == student.institution_id,
            Notification.type == NOTIF_DEADLINE,
        )
        .all()
    }

    created = 0
    for drive in drives:
        if drive.id in applied or drive.id in reminded:
            continue
        verdict = evaluate(db, drive_id=drive.id, student=student)
        if not (verdict.eligible and verdict.definitive):
            continue
        apply_by = drive.apply_by
        if apply_by is not None and apply_by.tzinfo is None:
            apply_by = apply_by.replace(tzinfo=UTC)
        days_left = max(0, (apply_by - now).days) if apply_by is not None else 0
        company = drive.company.name if drive.company else "the company"
        create(
            db,
            user_id=user.id,
            institution_id=student.institution_id,
            type=NOTIF_DEADLINE,
            title=f"Application deadline approaching: {drive.title}",
            body=(
                f"{drive.title} at {company} closes in "
                f"{days_left} day(s). Apply before the deadline."
            ),
            link=f"/opportunities/{drive.id}",
            payload={"drive_id": drive.id},
        )
        created += 1

    if created:
        db.commit()
    return created


def unsubscribe_target(user_id: str) -> None:
    """Future hook for per-student notification preferences."""
    _ = user_id