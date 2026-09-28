"""FastAPI dependency helpers: auth, RBAC, tenant isolation, pagination."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Query, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AuthenticationError, PayloadTooLargeError, PermissionError_
from app.core.rbac import Permission, has_permission
from app.core.security import TokenError, decode_token
from app.db.models import Student, User
from app.db.session import get_db
from app.services.audit import AuditContext


def enforce_request_content_length(request: Request, *, max_bytes: int) -> None:
    """Reject obviously oversized requests before the body is buffered.

    The declared Content-Length covers the whole multipart body, which includes
    boundary/header overhead beyond the file bytes themselves, so we allow a
    fixed slack above the hard per-file limit. The per-file size check after
    reading remains the authoritative second layer.
    """
    # 1 MiB is generous for multipart headers/boundaries; a single file using
    # our full allowance stays well below this threshold.
    threshold = max_bytes + (1 * 1024 * 1024)
    declared = request.headers.get("Content-Length")
    if declared is not None:
        try:
            declared_int = int(declared)
        except ValueError:
            return
        if declared_int > threshold:
            raise PayloadTooLargeError(
                f"Request body exceeds the {max_bytes // (1024 * 1024)}MB limit.",
                code="upload_too_large",
            )


@dataclass
class CurrentUser:
    user_id: str
    role: str
    institution_id: str
    actor: User | None = None

    @property
    def is_admin(self) -> bool:
        return self.role in {"placement_admin", "super_admin"}


def _bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise AuthenticationError("Missing Authorization header.")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise AuthenticationError("Authorization must use the Bearer scheme.")
    return token


def get_current_user(
    authorization: Annotated[str | None, Header()] = None,
    db: Session = Depends(get_db),
) -> CurrentUser:
    token = _bearer_token(authorization)
    try:
        payload = decode_token(token, expected_type="access")
    except TokenError as exc:
        raise AuthenticationError(str(exc)) from exc

    user = db.get(User, payload.get("sub"))
    if user is None:
        raise AuthenticationError("Account no longer exists.")
    if not user.is_active:
        raise PermissionError_("Account is disabled.")
    institution_id = payload.get("institution_id")
    if not institution_id or institution_id != user.institution_id:
        # A token minted for another tenant must never grant access here.
        raise AuthenticationError("Token does not match your institution.")
    if payload.get("role") != user.role:
        raise AuthenticationError("Token role mismatch.")
    return CurrentUser(
        user_id=user.id, role=user.role, institution_id=user.institution_id, actor=user
    )


def require_permission(permission: Permission | str) -> Callable:
    """Dependency factory: require the permission after authenticating."""

    def _dep(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not has_permission(current.role, permission):
            raise PermissionError_(
                "You do not have permission to perform this action.",
                code="insufficient_permissions",
            )
        return current

    return _dep


def require_student(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    if current.role != "student":
        raise PermissionError_(
            "This endpoint is only available to student accounts.",
            code="student_only",
        )
    return current


def get_student_record(
    current: Annotated[CurrentUser, Depends(get_current_user)],
    db: Session = Depends(get_db),
) -> Student:
    """Resolve the Student row for the authenticated user (or fail hard)."""
    student = db.query(Student).filter(Student.user_id == current.user_id).first()
    if student is None or not student.is_active:
        raise PermissionError_("No active student profile is linked to this account.")
    # A student's profile must belong to the caller's institution.
    if student.institution_id != current.institution_id:
        raise PermissionError_("Profile institution mismatch.")
    return student


@dataclass
class Pagination:
    page: int
    limit: int
    offset: int


def get_pagination(
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=200)] = 10,
) -> Pagination:
    limit = min(limit, settings.pagination_max_limit)
    return Pagination(page=page, limit=limit, offset=(page - 1) * limit)


def get_actor_context(
    request: Request,
    current: CurrentUser = Depends(get_current_user),
) -> AuditContext:
    """Resolve the audit context from request headers."""
    forwarded = request.headers.get("X-Forwarded-For")
    ip = (forwarded.split(",")[0].strip() if forwarded else request.client.host if request.client else None) or None
    return AuditContext(
        actor_id=current.user_id,
        actor_email=current.actor.email if current.actor else None,
        actor_role=current.role,
        ip_address=ip,
        user_agent=request.headers.get("User-Agent"),
        institution_id=current.institution_id,
    )


def enforce_institution_scope(entity_inst: str, current_inst: str) -> None:
    """Call after loading a row whose institution_id must match the caller's."""
    if entity_inst != current_inst:
        raise PermissionError_("Resource belongs to another institution.")