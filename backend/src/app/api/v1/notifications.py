"""Notification endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import (
    CurrentUser,
    Pagination,
    get_actor_context,
    get_current_user,
    get_pagination,
)
from app.core.config import settings
from app.core.ratelimit import route_limit
from app.db.session import get_db
from app.schemas.applications import NotificationMarkRead, NotificationRead, PaginatedNotifications
from app.services import notifications as notif_service
from app.services.audit import record

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=PaginatedNotifications)
def list_notifications(
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    pagination: Pagination = Depends(get_pagination),
    unread_only: bool = False,
) -> PaginatedNotifications:
    rows, total, unread_count = notif_service.list_for_user(
        db,
        user_id=current.user_id,
        institution_id=current.institution_id,
        page=pagination.page,
        limit=pagination.limit,
        unread_only=unread_only,
    )
    return PaginatedNotifications(
        items=[_to_read(n) for n in rows],
        total=total,
        page=pagination.page,
        limit=pagination.limit,
        unread_count=unread_count,
    )


@router.post("/mark-read", response_model=dict)
@route_limit(settings.rate_limit_write)
def mark_read(
    body: NotificationMarkRead,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    count = notif_service.mark_read(
        db,
        user_id=current.user_id,
        institution_id=current.institution_id,
        ids=body.ids,
    )
    record(
        db,
        action="notification.marked_read",
        context=get_actor_context(request, current),
        entity_type="notification",
        detail={"count": count},
    )
    db.commit()
    return {"marked_read": count}


def _to_read(n) -> NotificationRead:
    return NotificationRead(
        id=n.id,
        type=n.type,
        title=n.title,
        body=n.body,
        link=n.link,
        payload=n.payload or {},
        is_read=n.is_read,
        created_at=n.created_at,
    )