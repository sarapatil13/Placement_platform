"""Authentication endpoints."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.core.config import settings
from app.core.errors import AuthenticationError, PermissionError_
from app.core.ratelimit import route_limit
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    decode_token_loose,
)
from app.db.models import User
from app.db.session import get_db
from app.schemas.auth import (
    AccessToken,
    ActivateAccountRequest,
    ChangePasswordRequest,
    LoginRequest,
    LogoutRequest,
    Message,
    RefreshRequest,
    TokenPair,
    WhoAmISchema,
)
from app.services import tokens as token_service
from app.services import users as user_service
from app.services.audit import AuditContext, record

router = APIRouter(prefix="/auth", tags=["auth"])

# httpOnly refresh-token cookie. Path is scoped to the auth API so the cookie is
# never presented on other endpoints. SameSite=Strict plus a required
# X-Requested-With header on cookie-based refreshes keeps the cookie path CSRF-safe.
REFRESH_COOKIE = "pp_refresh"
COOKIE_PATH = "/api/v1/auth"
CSRF_HEADER = "x-requested-with"


def _refresh_cookie_seconds() -> int:
    return settings.refresh_token_expire_days * 86400


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=refresh_token,
        max_age=_refresh_cookie_seconds(),
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
        path=COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE, path=COOKIE_PATH)


def _token_pair(user: User) -> dict:
    institution_id = user.institution_id
    access = create_access_token(
        role=user.role, institution_id=institution_id, extra_claims={"sub": user.id}
    )
    refresh = create_refresh_token(
        role=user.role, institution_id=institution_id, sub=user.id
    )
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "expires_in": settings.access_token_expire_minutes * 60,
    }


@router.post("/login", response_model=AccessToken)
@route_limit(settings.rate_limit_auth)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AccessToken:
    user = user_service.authenticate(
        db,
        email=body.email,
        password=body.password,
        institution_id=settings.institution.code,
    )
    actor = AuditContext(
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
        institution_id=user.institution_id,
    )
    record(db, action="auth.login.success", context=actor, entity_type="user", entity_id=user.id)
    db.commit()
    pair = _token_pair(user)
    _set_refresh_cookie(response, pair["refresh_token"])
    return AccessToken(
        access_token=pair["access_token"],
        token_type="bearer",
        expires_in=pair["expires_in"],
        user=_to_whoami(user),
    )


@router.post("/refresh", response_model=TokenPair)
@route_limit("60/minute")
def refresh(
    body: RefreshRequest | None = None,
    request: Request = None,  # type: ignore[assignment]
    response: Response = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
) -> TokenPair:
    token = None
    if body is not None and body.refresh_token:
        token = body.refresh_token
    elif request is not None:
        token = request.cookies.get(REFRESH_COOKIE)
        if token and request.headers.get(CSRF_HEADER, "").lower() != "xmlhttprequest":
            # Cookie-based refresh must come from our own SPA, not a cross-site
            # forged request. The marker header cannot be set cross-origin.
            raise PermissionError_(
                "Refresh requests require the expected client header.",
                code="csrf_protection",
            )
    if not token:
        raise AuthenticationError("Missing refresh token.")
    return _refresh_with_token(token, request, db, response=response)


def _refresh_with_token(
    token: str,
    request: Request | None,
    db: Session,
    *,
    response: Response | None = None,
) -> TokenPair:
    from app.core.security import TokenError

    try:
        payload = decode_token(token, expected_type="refresh")
    except TokenError as exc:
        raise AuthenticationError(str(exc)) from exc
    if token_service.is_refresh_token_revoked(db, jti=payload["jti"]):
        raise AuthenticationError(
            "Refresh token has been revoked. Sign in again.",
            code="refresh_token_revoked",
        )
    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise AuthenticationError("Account no longer exists.")
    if payload.get("institution_id") != user.institution_id:
        raise AuthenticationError("Token does not match your institution.")

    pair = _token_pair(user)
    # Rotation: the presented token can never be used again, so a stolen or
    # replayed copy of it cannot mint further sessions.
    expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
    token_service.revoke_refresh_token(
        db, jti=payload["jti"], user_id=user.id, expires_at=expires_at
    )
    actor = AuditContext(
        actor_id=user.id, actor_email=user.email, actor_role=user.role,
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("User-Agent") if request else None,
        institution_id=user.institution_id,
    )
    record(db, action="auth.refresh", context=actor, entity_type="user", entity_id=user.id)
    db.commit()
    if response is not None:
        _set_refresh_cookie(response, pair["refresh_token"])
    return TokenPair(
        access_token=pair["access_token"],
        refresh_token=pair["refresh_token"],
        token_type="bearer",
        expires_in=pair["expires_in"],
        user=_to_whoami(user),
    )


@router.get("/me", response_model=WhoAmISchema)
def me(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> WhoAmISchema:
    user = db.get(User, current.user_id)
    if user is None:
        raise AuthenticationError("Account no longer exists.")
    return _to_whoami(user)


@router.post("/logout", response_model=Message)
@route_limit(settings.rate_limit_write)
def logout(
    body: LogoutRequest | None = None,
    request: Request = None,  # type: ignore[assignment]
    response: Response = None,  # type: ignore[assignment]
    db: Session = Depends(get_db),
) -> Message:
    """Revoke the refresh token (from the body or the cookie).

    Deliberately does NOT require a valid access token: logout must still work
    after the short-lived access token has expired, and it must revoke the
    long-lived credential even if the access token is already dead.
    """
    refresh_token = None
    if body is not None and body.refresh_token:
        refresh_token = body.refresh_token
    elif request is not None:
        refresh_token = request.cookies.get(REFRESH_COOKIE)

    if refresh_token:
        payload = decode_token_loose(refresh_token, expected_type="refresh")
        if payload is not None:
            expires_at = datetime.fromtimestamp(payload["exp"], tz=UTC)
            token_service.revoke_refresh_token(
                db,
                jti=payload["jti"],
                user_id=str(payload.get("sub") or ""),
                expires_at=expires_at,
            )
            actor_id = str(payload.get("sub") or "")
            actor_email = None
            if actor_id:
                existing = db.get(User, actor_id)
                if existing is not None:
                    actor_email = existing.email
            actor = AuditContext(
                actor_id=actor_id or None,
                actor_email=actor_email,
                actor_role=str(payload.get("role") or ""),
                ip_address=request.client.host if request and request.client else None,
                user_agent=request.headers.get("User-Agent") if request else None,
                institution_id=payload.get("institution_id"),
            )
            record(
                db,
                action="auth.logout",
                context=actor,
                entity_type="user",
                entity_id=str(payload.get("sub") or ""),
            )
            db.commit()

    if response is not None:
        _clear_refresh_cookie(response)
    return Message(message="Logged out.")


def get_actor_context_short(current: CurrentUser) -> AuditContext:
    return AuditContext(
        actor_id=current.user_id,
        actor_email=current.actor.email if current.actor else None,
        actor_role=current.role,
        ip_address=None,
        user_agent=None,
        institution_id=current.institution_id,
    )


@router.post("/activate", response_model=AccessToken)
@route_limit(settings.rate_limit_auth)
def activate(
    body: ActivateAccountRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> AccessToken:
    user = user_service.activate(
        db,
        token=body.token,
        full_name=body.full_name,
        new_password=body.new_password,
        institution_id=settings.institution.code,
        student_self_fields=body.student_self_fields,
    )
    actor = AuditContext(
        actor_id=user.id, actor_email=user.email, actor_role=user.role,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"), institution_id=user.institution_id,
    )
    record(db, action="auth.activated", context=actor, entity_type="user", entity_id=user.id)
    db.commit()
    pair = _token_pair(user)
    _set_refresh_cookie(response, pair["refresh_token"])
    return AccessToken(
        access_token=pair["access_token"], token_type="bearer",
        expires_in=pair["expires_in"], user=_to_whoami(user),
    )


@router.post("/change-password", response_model=Message)
@route_limit(settings.rate_limit_write)
def change_password(
    body: ChangePasswordRequest,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Message:
    user = db.get(User, current.user_id)
    if user is None:
        raise AuthenticationError("Account no longer exists.")
    user_service.change_password(
        db, user=user, current_password=body.current_password, new_password=body.new_password,
    )
    return Message(message="Password changed.")


def _to_whoami(user: User) -> WhoAmISchema:
    return WhoAmISchema(
        id=user.id, email=user.email, full_name=user.full_name, role=user.role,
        institution_id=user.institution_id,
        institution_code=settings.institution.code,
        is_active=user.is_active, must_change_password=user.must_change_password,
    )