"""Student provisioning and profile service."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError
from app.core.errors import ValidationError as _ValidationError
from app.core.security import (
    generate_opaque_token,
    hash_password,
    hash_token,
)
from app.db.models import Department, Skill, Student, StudentSkill, User
from app.services.audit import AuditContext, record


def provision_student(
    db: Session,
    *,
    institution_id: str,
    college_id: str,
    email: str,
    full_name: str,
    department_code: str,
    batch_year: int,
    cgpa: float | None,
    backlog_count: int,
    active_backlogs: int,
    gender: str | None = None,
    date_of_birth=None,
    phone: str | None = None,
    academic_data_verified: bool = True,
    temporary_password: str | None = None,
    actor_ctx: AuditContext | None = None,
    send_activation: bool = False,
) -> tuple[User, Student, str | None]:
    """Create a student + login account. Returns (user, student, activation_token).

    Raises ConflictError when the college_id or email already exists in the
    institution; the caller decides whether to skip.
    """
    email = email.lower()
    if db.query(User).filter(
        User.institution_id == institution_id, User.email == email
    ).first():
        raise ConflictError(f"Email already exists in this institution: {email}.")
    if db.query(Student).filter(
        Student.institution_id == institution_id, Student.college_id == college_id
    ).first():
        raise ConflictError(f"College ID already exists: {college_id}.")

    department = _get_department(db, institution_id, department_code)

    activation_token: str | None = None
    must_change = False
    if temporary_password:
        password_hash = hash_password(temporary_password)
    elif send_activation and settings.institution.allow_self_registration:
        activation_token = generate_opaque_token()
        password_hash = hash_password(_temp_hash())
        must_change = True
    else:
        # No credential supplied and activation is off: issue a random
        # throwaway hash so there is no shared default password anywhere.
        # The account must go through the reset/activation flow to log in.
        password_hash = hash_password(_temp_hash())
        must_change = True

    user = User(
        institution_id=institution_id,
        email=email,
        password_hash=password_hash,
        role="student",
        full_name=full_name,
        phone=phone,
        must_change_password=must_change,
    )
    db.add(user)
    db.flush()

    student = Student(
        institution_id=institution_id,
        user_id=user.id,
        department_id=department.id,
        college_id=college_id.upper(),
        batch_year=batch_year,
        cgpa=cgpa,
        backlog_count=backlog_count or 0,
        active_backlogs=active_backlogs or 0,
        gender=gender,
        date_of_birth=date_of_birth,
        phone=phone,
        academic_data_verified=academic_data_verified,
        cgpa_source="institution" if cgpa is not None else None,
    )
    db.add(student)
    db.flush()

    if activation_token:
        user.activation_token_hash = hash_token(activation_token)
        user.activation_expires_at = _activation_expiry()
        db.add(user)

    record(
        db,
        action="student.provisioned",
        context=actor_ctx,
        entity_type="student",
        entity_id=student.id,
        detail={"email": email, "college_id": college_id, "department": department_code},
    )
    db.flush()
    return user, student, activation_token


def _temp_hash() -> str:
    import secrets

    return secrets.token_urlsafe(24)


def _activation_expiry() -> datetime:
    from datetime import UTC, timedelta

    return datetime.now(UTC) + timedelta(days=7)


def update_institutional_fields(
    db: Session,
    *,
    student: Student,
    institution_id: str,
    values: dict,
    actor_ctx: AuditContext | None = None,
) -> Student:
    """Admin-only update of authoritative academic fields. Every change is
    audited with before/after values."""
    allowed = {
        "college_id",
        "department_code",
        "batch_year",
        "cgpa",
        "cgpa_source",
        "backlog_count",
        "active_backlogs",
        "date_of_birth",
        "gender",
        "academic_data_verified",
        "is_active",
    }
    provided = {
        k: v
        for k, v in values.items()
        if k in allowed
        and (v is not None or k in {"academic_data_verified", "is_active", "cgpa"})
    }
    if not provided:
        raise _ValidationError("No supported institutional fields provided.")

    before = {
        "college_id": student.college_id,
        "batch_year": student.batch_year,
        "cgpa": student.cgpa,
        "backlog_count": student.backlog_count,
        "active_backlogs": student.active_backlogs,
        "academic_data_verified": student.academic_data_verified,
    }
    if "department_code" in values and values["department_code"]:
        department = _get_department(db, institution_id, values["department_code"])
        if department.id != student.department_id:
            before["department"] = student.department.code
            student.department_id = department.id
    for key, value in provided.items():
        if key in {"department_code"}:
            continue
        setattr(student, key, value)
    record(
        db,
        action="student.institutional_updated",
        context=actor_ctx,
        entity_type="student",
        entity_id=student.id,
        outcome="success",
        detail={"changed": {k: {"from": before.get(k), "to": provided.get(k)} for k in provided if k in before}},
    )
    db.commit()
    db.refresh(student)
    return student


def update_self_profile(db: Session, *, student: Student, values: dict, actor_ctx=None) -> Student:
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
    updated = {k: v for k, v in values.items() if k in allowed}

    if len(updated) != len(values):
        unexpected = set(values) - set(allowed)
        raise _ValidationError(
            "Students cannot modify institution-owned fields: " + ", ".join(sorted(unexpected))
        )
    for key, value in updated.items():
        setattr(student, key, value)
    record(
        db,
        action="student.self_updated",
        context=actor_ctx,
        entity_type="student",
        entity_id=student.id,
        detail={"fields": sorted(updated)},
    )
    db.commit()
    db.refresh(student)
    return student


def replace_skills(
    db: Session, *, student: Student, skills: list[dict], actor_ctx: AuditContext | None = None
) -> list[StudentSkill]:
    """Idempotently sync the student's declared skills. Verifies nothing, records source."""
    db.query(StudentSkill).filter(StudentSkill.student_id == student.id).delete()
    db.flush()
    rows: list[StudentSkill] = []
    for item in skills:
        name = (item.get("name") or "").strip()
        if not name:
            continue
        skill = _get_or_create_skill(db, student.institution_id, name)
        row = StudentSkill(
            institution_id=student.institution_id,
            student_id=student.id,
            skill_id=skill.id,
            proficiency=item.get("proficiency"),
            years_experience=item.get("years_experience"),
            source="self_declared",
        )
        db.add(row)
        rows.append(row)
    db.flush()
    record(
        db,
        action="student.skills_replaced",
        context=actor_ctx,
        entity_type="student",
        entity_id=student.id,
        detail={"skill_count": len(rows)},
    )
    db.commit()
    return rows


def add_skill(db: Session, *, student: Student, name: str, proficiency=None, years=None) -> StudentSkill:
    skill = _get_or_create_skill(db, student.institution_id, name)
    existing = (
        db.query(StudentSkill)
        .filter(StudentSkill.student_id == student.id, StudentSkill.skill_id == skill.id)
        .first()
    )
    if existing:
        existing.proficiency = proficiency or existing.proficiency
        existing.years_experience = years or existing.years_experience
        return existing
    row = StudentSkill(
        institution_id=student.institution_id,
        student_id=student.id,
        skill_id=skill.id,
        proficiency=proficiency,
        years_experience=years,
        source="self_declared",
    )
    db.add(row)
    return row


def get_drive_skill_names(db: Session, drive_id: str) -> list[str]:
    from app.db.models import DriveSkill

    return [row.skill.name for row in db.query(DriveSkill).filter(DriveSkill.drive_id == drive_id).all()]


def _get_department(db: Session, institution_id: str, code: str) -> Department:
    department = (
        db.query(Department)
        .filter(
            Department.institution_id == institution_id,
            Department.code == code.strip().upper(),
        )
        .first()
    )
    if department is None:
        raise NotFoundError(f"Unknown department code '{code.upper()}'.")
    return department


def _get_or_create_skill(db: Session, institution_id: str, name: str) -> Skill:
    import re

    normalized = re.sub(r"[\s._-]+", " ", name.strip().lower())
    skill = (
        db.query(Skill)
        .filter(
            Skill.institution_id == institution_id,
            Skill.normalized_name == normalized,
        )
        .first()
    )
    if skill:
        return skill
    skill = Skill(institution_id=institution_id, name=name.strip(), normalized_name=normalized)
    db.add(skill)
    db.flush()
    return skill