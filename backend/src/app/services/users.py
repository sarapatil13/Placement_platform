"""Account/user service: activation, password changes, login bookkeeping."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AuthenticationError, ValidationError
from app.core.security import (
    generate_opaque_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.db.models import User
from app.services.audit import AuditContext, record

MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15


def _as_utc(value: datetime | None) -> datetime | None:
    """SQLite stores naive UTC; resolve both aware and naive to aware UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def init_institution(db: Session) -> None:
    """Ensure the default institution exists (idempotent). Used by seeder."""
    from app.db.models import Institution

    if db.query(Institution).filter_by(id=settings.institution.code).first():
        return
    inst = Institution(
        id=settings.institution.code,
        name=settings.institution.name,
        short_name=settings.institution.short_name,
        code=settings.institution.code,
        city=settings.institution.city,
        contact_email=settings.institution.contact_email,
        grading_scale_max=settings.institution.grading_scale_max,
        identity_issuer=settings.institution.identity_issuer,
    )
    db.add(inst)
    db.flush()


def get_user_by_email(db: Session, email: str, institution_id: str) -> User | None:
    return (
        db.query(User)
        .filter(
            User.email == email.lower(),
            User.institution_id == institution_id,
        )
        .first()
    )


def authenticate(
    db: Session,
    *,
    email: str,
    password: str,
    institution_id: str,
) -> User:
    user = get_user_by_email(db, email, institution_id)
    if user is None:
        # Constant-shape failure: same error for unknown email vs wrong password.
        raise AuthenticationError("Invalid email or password.")

    locked_until = _as_utc(user.locked_until)
    if locked_until and locked_until > datetime.now(UTC):
        remain = int((locked_until - datetime.now(UTC)).total_seconds() // 60)
        raise AuthenticationError(
            f"Account is temporarily locked. Try again in about {max(remain, 1)} minute(s)."
        )

    if not verify_password(password, user.password_hash):
        user.failed_login_count += 1
        if user.failed_login_count >= MAX_FAILED_LOGINS:
            user.locked_until = datetime.now(UTC) + timedelta(minutes=LOCKOUT_MINUTES)
            user.failed_login_count = 0
        db.commit()
        raise AuthenticationError("Invalid email or password.")

    if not user.is_active:
        raise AuthenticationError("Account is disabled. Contact the placement cell.")

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = datetime.now(UTC)
    db.commit()
    return user


def create_activation(
    db: Session,
    *,
    user: User,
    actor_ctx: AuditContext | None = None,
) -> str:
    """Generate an activation token for a provisioned account. Returns the raw
    token (shown once) and stores only its hash."""
    raw = generate_opaque_token()
    user.activation_token_hash = hash_token(raw)
    user.activation_expires_at = datetime.now(UTC) + timedelta(days=7)
    user.must_change_password = True
    db.add(user)
    record(
        db,
        action="user.activation_issued",
        context=actor_ctx,
        entity_type="user",
        entity_id=user.id,
        detail={"email": user.email},
    )
    db.flush()
    return raw


def activate(
    db: Session,
    *,
    token: str,
    full_name: str,
    new_password: str,
    institution_id: str,
    student_self_fields: dict | None = None,
) -> User:
    digest = hash_token(token)
    user = db.query(User).filter(User.activation_token_hash == digest).first()
    if user is None:
        raise ValidationError("Activation token is invalid.")
    if user.institution_id != institution_id:
        raise ValidationError("Activation token is invalid.")
    expires_at = _as_utc(user.activation_expires_at)
    if expires_at and expires_at < datetime.now(UTC):
        raise ValidationError("Activation token has expired. Contact the placement cell.")
    if not user.must_change_password:
        raise ValidationError("This account has already been activated.")

    from app.core.security import password_policy_errors

    errors = password_policy_errors(new_password, full_name=full_name, email=user.email)
    if errors:
        raise ValidationError("; ".join(errors))
    _ = student_self_fields  # student profile self-fields are handled by students service

    user.password_hash = hash_password(new_password)
    user.must_change_password = False
    user.activation_token_hash = None
    user.activation_expires_at = None
    user.full_name = full_name or user.full_name
    if student_self_fields:
        _apply_student_self_fields(db, user.id, student_self_fields)
    db.commit()
    db.refresh(user)
    return user


def _apply_student_self_fields(db: Session, user_id: str, fields: dict) -> None:
    """Apply only the whitelisted contact fields during activation."""
    allowed = {
        "phone",
        "profile_headline",
        "about",
        "portfolio_url",
        "linkedin_url",
        "github_url",
        "location",
        "resume_headline",
    }
    from app.db.models import Student

    student = db.query(Student).filter(Student.user_id == user_id).first()
    if student is None:
        return
    for key, value in fields.items():
        if key in allowed:
            setattr(student, key, value)


def change_password(
    db: Session,
    *,
    user: User,
    current_password: str,
    new_password: str,
    actor_ctx: AuditContext | None = None,
) -> User:
    if not verify_password(current_password, user.password_hash):
        raise AuthenticationError("Current password is incorrect.")
    from app.core.security import password_policy_errors

    errors = password_policy_errors(new_password, full_name=user.full_name, email=user.email)
    if errors:
        raise ValidationError("; ".join(errors))
    user.password_hash = hash_password(new_password)
    db.add(user)
    record(
        db,
        action="user.password_changed",
        context=actor_ctx,
        entity_type="user",
        entity_id=user.id,
    )
    db.commit()
    db.refresh(user)
    return user