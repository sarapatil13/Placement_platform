"""ORM models.

Layering: institutions -> departments -> users -> students, then companies ->
drives -> criteria, then resumes/skills, then applications/history, then
notifications, AI analyses, and audit logs.

Two rules enforced structurally:
1. Every student-scoped row carries `institution_id` so tenant isolation is a
   filterable column, not an assumption.
2. Authoritative academic fields (college_id, department_id, batch, cgpa,
   backlog_count) live on `Student` and are only writable by placement-cell
   code paths. The API layer refuses student-originated writes to them.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.crypto import EncryptedString
from app.db.base import Base, id_column, timestamp_column, updated_at_column, utcnow

# --------------------------------------------------------------------------- #
# Enumerated values (stored as strings for painless migrations)
# --------------------------------------------------------------------------- #
USER_ACTIVE = "active"
USER_SUSPENDED = "suspended"
USER_DISABLED = "disabled"

DRIVE_DRAFT = "draft"
DRIVE_PUBLISHED = "published"
DRIVE_CLOSED = "closed"
DRIVE_ARCHIVED = "archived"
DRIVE_STATUSES = (DRIVE_DRAFT, DRIVE_PUBLISHED, DRIVE_CLOSED, DRIVE_ARCHIVED)

ROUND_ONLINE_ASSESSMENT = "online_assessment"
ROUND_TECHNICAL_INTERVIEW = "technical_interview"
ROUND_HR_INTERVIEW = "hr_interview"
ROUND_GROUP_DISCUSSION = "group_discussion"
ROUND_OTHER = "other"
ROUND_TYPES = (
    ROUND_ONLINE_ASSESSMENT,
    ROUND_TECHNICAL_INTERVIEW,
    ROUND_HR_INTERVIEW,
    ROUND_GROUP_DISCUSSION,
    ROUND_OTHER,
)

APP_APPLIED = "applied"
APP_IN_REVIEW = "in_review"
APP_SHORTLISTED = "shortlisted"
APP_INTERVIEW = "interview"
APP_OFFERED = "offered"
APP_REJECTED = "rejected"
APP_WITHDRAWN = "withdrawn"
APP_OFFER_ACCEPTED = "offer_accepted"
APP_OFFER_DECLINED = "offer_declined"
# Forward-only transition graph. Enforced in app.services.applications.
APP_TRANSITIONS: dict[str, set[str]] = {
    APP_APPLIED: {APP_IN_REVIEW, APP_WITHDRAWN, APP_REJECTED},
    APP_IN_REVIEW: {APP_SHORTLISTED, APP_REJECTED, APP_WITHDRAWN},
    APP_SHORTLISTED: {APP_INTERVIEW, APP_REJECTED, APP_WITHDRAWN},
    APP_INTERVIEW: {APP_OFFERED, APP_REJECTED, APP_WITHDRAWN},
    APP_OFFERED: {APP_OFFER_ACCEPTED, APP_OFFER_DECLINED, APP_REJECTED},
    APP_OFFER_ACCEPTED: set(),
    APP_OFFER_DECLINED: set(),
    APP_REJECTED: set(),
    APP_WITHDRAWN: set(),
}
APP_TERMINAL = {s for s, nxt in APP_TRANSITIONS.items() if not nxt}
APP_ACTIVE = {APP_APPLIED, APP_IN_REVIEW, APP_SHORTLISTED, APP_INTERVIEW, APP_OFFERED}

CRITERIA_CGPA_MIN = "cgpa_min"
CRITERIA_CGPA_MAX = "cgpa_max"
CRITERIA_BACKLOG_MAX = "backlog_max"
CRITERIA_DEPARTMENTS = "departments"
CRITERIA_BATCH_YEARS = "batch_years"
CRITERIA_SKILL_MIN_MATCH = "skill_min_match"
CRITERIA_AGE_MAX = "age_max"
CRITERIA_GENDER = "gender"
CRITERIA_PERCENTILE_MIN = "percentile_min"
CRITERIA_CRITERIA_TYPES = (
    CRITERIA_CGPA_MIN,
    CRITERIA_CGPA_MAX,
    CRITERIA_BACKLOG_MAX,
    CRITERIA_DEPARTMENTS,
    CRITERIA_BATCH_YEARS,
    CRITERIA_SKILL_MIN_MATCH,
    CRITERIA_AGE_MAX,
    CRITERIA_GENDER,
    CRITERIA_PERCENTILE_MIN,
)


class Institution(Base):
    """A university/college tenant. All other rows hang off one of these."""

    __tablename__ = "institutions"

    id: Mapped[str] = id_column()
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    short_name: Mapped[str] = mapped_column(String(50), nullable=False)
    code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    city: Mapped[str | None] = mapped_column(String(120))
    contact_email: Mapped[str] = mapped_column(String(200), nullable=False)
    grading_scale_max: Mapped[float] = mapped_column(Float, default=10.0, nullable=False)
    identity_issuer: Mapped[str] = mapped_column(String(100), nullable=False)
    settings: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = updated_at_column()

    departments: Mapped[list[Department]] = relationship(
        back_populates="institution", cascade="all, delete-orphan"
    )


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("institution_id", "code", name="uq_departments_institution_id_code"),
        Index("ix_departments_institution_id_name", "institution_id", "name"),
    )

    id: Mapped[str] = id_column()
    institution_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    degree: Mapped[str | None] = mapped_column(String(100))
    # Denormalised convenience flags so eligibility config stays declarative.
    is_technical: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = timestamp_column()

    institution: Mapped[Institution] = relationship(back_populates="departments")
    students: Mapped[list[Student]] = relationship(back_populates="department")


class User(Base):
    """Login identity. Separate from Student so admins have no student record."""

    __tablename__ = "users"
    __table_args__ = (Index("ix_users_institution_id_email", "institution_id", "email"),)

    id: Mapped[str] = id_column()
    institution_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    phone: Mapped[str | None] = mapped_column(EncryptedString(32))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Students may not self-register; an admin-provisioned invite token is set
    # when a student is imported and must be exchanged for a password.
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    activation_token_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    activation_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_login_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = updated_at_column()

    student: Mapped[Student | None] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )

    @property
    def is_admin(self) -> bool:
        return self.role in {"placement_admin", "super_admin"}


class Student(Base):
    """Student profile including institution-owned academic data.

    Authoritative fields (college_id, department_id, batch_year, cgpa,
    backlog_count, active_backlogs) are never accepted from student-facing
    request bodies; see `app.api.v1.students` and the RBAC permission
    UPDATE_INSTITUTIONAL_STUDENT_FIELDS.
    """

    __tablename__ = "students"
    __table_args__ = (
        UniqueConstraint("institution_id", "college_id", name="uq_students_institution_id_college_id"),
        CheckConstraint("cgpa IS NULL OR cgpa >= 0", name="cgpa_non_negative"),
        CheckConstraint("backlog_count IS NULL OR backlog_count >= 0", name="backlog_non_negative"),
        Index("ix_students_institution_id_department_id", "institution_id", "department_id"),
        Index("ix_students_institution_id_active", "institution_id", "is_active"),
    )

    id: Mapped[str] = id_column()
    institution_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    department_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("departments.id", ondelete="RESTRICT"), nullable=False
    )

    # --- institution-owned ---
    college_id: Mapped[str] = mapped_column(String(50), nullable=False)  # USN
    batch_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    cgpa: Mapped[float | None] = mapped_column(Float)  # nullable => eligibility inconclusive
    backlog_count: Mapped[int | None] = mapped_column(Integer, default=0, nullable=False)
    active_backlogs: Mapped[int | None] = mapped_column(Integer, default=0, nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    gender: Mapped[str | None] = mapped_column(String(20))
    # Marks the record as verified by placement cell; unverified CGPA cannot pass.
    academic_data_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    # Explicit unknown rather than a default, so missing data is distinguishable
    # from a genuine zero.
    cgpa_source: Mapped[str | None] = mapped_column(String(60))

    # --- student-editable ---
    phone: Mapped[str | None] = mapped_column(EncryptedString(32))
    profile_headline: Mapped[str | None] = mapped_column(String(200))
    about: Mapped[str | None] = mapped_column(Text)
    portfolio_url: Mapped[str | None] = mapped_column(String(400))
    linkedin_url: Mapped[str | None] = mapped_column(String(400))
    github_url: Mapped[str | None] = mapped_column(String(400))
    location: Mapped[str | None] = mapped_column(String(120))
    resume_headline: Mapped[str | None] = mapped_column(String(200))

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = updated_at_column()

    user: Mapped[User] = relationship(back_populates="student")
    department: Mapped[Department] = relationship(back_populates="students")
    resumes: Mapped[list[Resume]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )
    skills: Mapped[list[StudentSkill]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )
    applications: Mapped[list[Application]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = (
        UniqueConstraint("institution_id", "name", name="uq_companies_institution_id_name"),
        CheckConstraint(
            "reputation_score IS NULL OR (reputation_score >= 0 AND reputation_score <= 5)",
            name="reputation_range",
        ),
    )

    id: Mapped[str] = id_column()
    institution_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    website: Mapped[str | None] = mapped_column(String(400))
    industry: Mapped[str | None] = mapped_column(String(120))
    about: Mapped[str | None] = mapped_column(Text)
    logo_url: Mapped[str | None] = mapped_column(String(400))
    location: Mapped[str | None] = mapped_column(String(150))
    contact_email: Mapped[str] = mapped_column(String(254), nullable=False)
    contact_name: Mapped[str | None] = mapped_column(String(150))
    tiers: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    reputation_score: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = updated_at_column()

    drives: Mapped[list[PlacementDrive]] = relationship(back_populates="company")


class PlacementDrive(Base):
    """A recruiting opportunity = company + role + JD + eligibility criteria."""

    __tablename__ = "placement_drives"
    __table_args__ = (
        Index("ix_placement_drives_institution_id_status", "institution_id", "status"),
        Index("ix_placement_drives_institution_id_deadline", "institution_id", "apply_by"),
    )

    id: Mapped[str] = id_column()
    institution_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    company_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    role_title: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    jd_text: Mapped[str | None] = mapped_column(Text)
    jd_filename: Mapped[str | None] = mapped_column(String(255))
    jd_storage_path: Mapped[str | None] = mapped_column(String(500))
    employment_type: Mapped[str] = mapped_column(String(50), default="full_time", nullable=False)
    location: Mapped[str | None] = mapped_column(String(150))
    ctc_lpa: Mapped[str | None] = mapped_column(String(50))  # stored as text; ranges common
    stipend: Mapped[str | None] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default=DRIVE_DRAFT, nullable=False)
    # Set only after an admin confirms the AI extraction, or supplies values by hand.
    eligibility_confirmed: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    eligibility_confirmed_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL")
    )
    eligibility_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_ai_extraction_pending: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    apply_by: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    drive_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(32), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = updated_at_column()

    company: Mapped[Company] = relationship(back_populates="drives")
    criteria: Mapped[list[EligibilityCriterion]] = relationship(
        back_populates="drive", cascade="all, delete-orphan"
    )
    drive_skills: Mapped[list[DriveSkill]] = relationship(
        back_populates="drive", cascade="all, delete-orphan"
    )
    rounds: Mapped[list[DriveRound]] = relationship(
        back_populates="drive", cascade="all, delete-orphan", order_by="DriveRound.position"
    )
    applications: Mapped[list[Application]] = relationship(back_populates="drive")


class EligibilityCriterion(Base):
    """A single confirmed rule. All eligibility decisions trace back to these rows.

    `parameters` is a small JSON object typed by `criterion_type`; keeping it
    JSON means a new university can define a rule shape without a migration,
    while the engine remains the only interpreter.
    """

    __tablename__ = "eligibility_criteria"
    __table_args__ = (
        UniqueConstraint(
            "drive_id", "criterion_type", name="uq_eligibility_criteria_drive_id_criterion_type"
        ),
    )

    id: Mapped[str] = id_column()
    institution_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    drive_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("placement_drives.id", ondelete="CASCADE"), nullable=False
    )
    criterion_type: Mapped[str] = mapped_column(String(40), nullable=False)
    parameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    # Where this rule came from: admin_manual, ai_suggested_confirmed, institution_default.
    source: Mapped[str] = mapped_column(String(30), default="admin_manual", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    confirmed_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL")
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = updated_at_column()

    drive: Mapped[PlacementDrive] = relationship(back_populates="criteria")


class Skill(Base):
    """Canonical skill vocabulary, shared across resumes, drives, and students."""

    __tablename__ = "skills"
    __table_args__ = (
        UniqueConstraint("institution_id", "normalized_name", name="uq_skills_institution_id_normalized_name"),
    )

    id: Mapped[str] = id_column()
    institution_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = timestamp_column()

    student_skills: Mapped[list[StudentSkill]] = relationship(back_populates="skill")
    drive_skills: Mapped[list[DriveSkill]] = relationship(back_populates="skill")


class StudentSkill(Base):
    __tablename__ = "student_skills"
    __table_args__ = (
        UniqueConstraint("student_id", "skill_id", name="uq_student_skills_student_id_skill_id"),
        CheckConstraint(
            "proficiency IS NULL OR (proficiency >= 1 AND proficiency <= 5)",
            name="proficiency_range",
        ),
    )

    id: Mapped[str] = id_column()
    institution_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    # 1-5, self-declared or AI-suggested. Never authoritative for eligibility.
    proficiency: Mapped[int | None] = mapped_column(Integer)
    years_experience: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(30), default="self_declared", nullable=False)
    # Projects / certifications the student attached as evidence.
    projects: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    certifications: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = updated_at_column()

    student: Mapped[Student] = relationship(back_populates="skills")
    skill: Mapped[Skill] = relationship(back_populates="student_skills")


class DriveSkill(Base):
    """A skill the drive requires, with a weight for match scoring."""

    __tablename__ = "drive_skills"
    __table_args__ = (
        UniqueConstraint("drive_id", "skill_id", name="uq_drive_skills_drive_id_skill_id"),
    )

    id: Mapped[str] = id_column()
    institution_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    drive_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("placement_drives.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("skills.id", ondelete="CASCADE"), nullable=False
    )
    requirement: Mapped[str] = mapped_column(String(20), default="required", nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    min_proficiency: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = timestamp_column()

    drive: Mapped[PlacementDrive] = relationship(back_populates="drive_skills")
    skill: Mapped[Skill] = relationship(back_populates="drive_skills")


class DriveRound(Base):
    """Recruitment round for a placement drive."""

    __tablename__ = "drive_rounds"
    __table_args__ = (
        UniqueConstraint("drive_id", "position", name="uq_drive_rounds_drive_id_position"),
        Index("ix_drive_rounds_drive_id", "drive_id"),
    )

    id: Mapped[str] = id_column()
    institution_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    drive_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("placement_drives.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    round_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    topics: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    drive: Mapped[PlacementDrive] = relationship(back_populates="rounds")


class Resume(Base):
    __tablename__ = "resumes"
    __table_args__ = (Index("ix_resumes_student_id_is_primary", "student_id", "is_primary"),)

    id: Mapped[str] = id_column()
    institution_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(120), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    parse_status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    parse_error: Mapped[str | None] = mapped_column(String(300))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    parsed_skills: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = updated_at_column()

    student: Mapped[Student] = relationship(back_populates="resumes")


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("student_id", "drive_id", name="uq_applications_student_id_drive_id"),
        Index("ix_applications_drive_id_status", "drive_id", "status"),
        Index("ix_applications_institution_id_status", "institution_id", "status"),
    )

    id: Mapped[str] = id_column()
    institution_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    drive_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("placement_drives.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), default=APP_APPLIED, nullable=False)
    # Eligibility snapshot at registration time, so a later rule change does not
    # retroactively alter the record of why a student was allowed to apply.
    eligibility_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, nullable=False
    )
    resume_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("resumes.id", ondelete="SET NULL")
    )
    # Frozen copy of the resume text sent with the application, for recruiters.
    resume_snapshot_text: Mapped[str | None] = mapped_column(Text)
    cover_note: Mapped[str | None] = mapped_column(Text)
    withdrawn_reason: Mapped[str | None] = mapped_column(String(300))
    applied_at: Mapped[datetime] = timestamp_column()
    updated_at: Mapped[datetime] = updated_at_column()
    created_at: Mapped[datetime] = timestamp_column()

    student: Mapped[Student] = relationship(back_populates="applications")
    drive: Mapped[PlacementDrive] = relationship(back_populates="applications")
    status_history: Mapped[list[ApplicationStatusHistory]] = relationship(
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationStatusHistory.created_at",
    )


class ApplicationStatusHistory(Base):
    """Append-only status timeline. Status is never mutated in place."""

    __tablename__ = "application_status_history"
    __table_args__ = (Index("ix_application_status_history_application_id", "application_id"),)

    id: Mapped[str] = id_column()
    institution_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    application_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("applications.id", ondelete="CASCADE"), nullable=False
    )
    from_status: Mapped[str | None] = mapped_column(String(30))
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    changed_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL")
    )
    changed_by_role: Mapped[str | None] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(String(500))
    # True when the student initiated the change (e.g. withdrawal).
    is_student_initiated: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    created_at: Mapped[datetime] = timestamp_column()

    application: Mapped[Application] = relationship(back_populates="status_history")


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_id_read", "user_id", "is_read"),)

    id: Mapped[str] = id_column()
    institution_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    link: Mapped[str | None] = mapped_column(String(400))
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = timestamp_column()


class AIAnalysis(Base):
    """Persisted AI output.

    Every row records the model, the validated schema name, and the raw response
    so a bad extraction can be audited after the fact. `confirmed_by`/`confirmed_at`
    record human sign-off for the two places AI informs institutional decisions
    (JD extraction and drive criteria).
    """

    __tablename__ = "ai_analyses"
    __table_args__ = (
        Index("ix_ai_analyses_student_id_created", "student_id", "created_at"),
        Index("ix_ai_analyses_drive_id_created", "drive_id", "created_at"),
    )

    id: Mapped[str] = id_column()
    institution_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("institutions.id", ondelete="CASCADE"), nullable=False
    )
    analysis_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    student_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("students.id", ondelete="CASCADE")
    )
    drive_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("placement_drives.id", ondelete="CASCADE")
    )
    resume_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("resumes.id", ondelete="SET NULL")
    )
    application_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("applications.id", ondelete="CASCADE")
    )
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(80), nullable=False)
    # Always the validated, typed result. Never an unparsed blob.
    result: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    # Retained for debugging only; never returned by the API.
    raw_response: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="succeeded", nullable=False)
    error: Mapped[str | None] = mapped_column(String(300))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    tokens_used: Mapped[int | None] = mapped_column(Integer)
    # Advisory skills are never authoritative; kept for the admin confirmation flow.
    requires_confirmation: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    confirmed_by: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL")
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = timestamp_column()


class AuditLog(Base):
    """Append-only record of every state change and privileged read.

    Deliberately never updated or deleted by application code.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_institution_id_created", "institution_id", "created_at"),
        Index("ix_audit_logs_actor_id_created", "actor_id", "created_at"),
        Index("ix_audit_logs_action", "action"),
    )

    id: Mapped[str] = id_column()
    institution_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("institutions.id", ondelete="SET NULL")
    )
    actor_id: Mapped[str | None] = mapped_column(String(32), index=True)
    actor_email: Mapped[str | None] = mapped_column(String(254))
    actor_role: Mapped[str | None] = mapped_column(String(30))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(32))
    # Forged or stolen token carries no institution context; recorded as null.
    outcome: Mapped[str] = mapped_column(String(20), default="success", nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(String(300))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = timestamp_column()


class RevokedRefreshToken(Base):
    """Server-side denylist for refresh tokens (keyed by decoded JTI).

    Refresh tokens are short-lived JWTs; revoking their ``jti`` until natural
    expiry implements logout, rotation, and replay protection without changing
    token lifetime semantics. Rows are expired (token ``exp``) and pruned
    opportunistically -- they never authorise anything after ``created_at``.
    """

    __tablename__ = "revoked_refresh_tokens"
    __table_args__ = (
        Index("ix_revoked_refresh_tokens_user_id", "user_id"),
        Index("ix_revoked_refresh_tokens_expires_at", "expires_at"),
    )

    id: Mapped[str] = id_column()
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    jti_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime] = timestamp_column()


__all__ = [
    "APP_ACTIVE",
    "APP_APPLIED",
    "APP_IN_REVIEW",
    "APP_INTERVIEW",
    "APP_OFFER_ACCEPTED",
    "APP_OFFER_DECLINED",
    "APP_OFFERED",
    "APP_REJECTED",
    "APP_SHORTLISTED",
    "APP_TERMINAL",
    "APP_TRANSITIONS",
    "APP_WITHDRAWN",
    "AIAnalysis",
    "Application",
    "ApplicationStatusHistory",
    "AuditLog",
    "Company",
    "CRITERIA_AGE_MAX",
    "CRITERIA_BACKLOG_MAX",
    "CRITERIA_BATCH_YEARS",
    "CRITERIA_CGPA_MAX",
    "CRITERIA_CGPA_MIN",
    "CRITERIA_DEPARTMENTS",
    "CRITERIA_GENDER",
    "CRITERIA_PERCENTILE_MIN",
    "CRITERIA_SKILL_MIN_MATCH",
    "Department",
    "DRIVE_ARCHIVED",
    "DRIVE_CLOSED",
    "DRIVE_DRAFT",
    "DRIVE_PUBLISHED",
    "DriveSkill",
    "DriveRound",
    "EligibilityCriterion",
    "Institution",
    "Notification",
    "PlacementDrive",
    "Resume",
    "RevokedRefreshToken",
    "ROUND_GROUP_DISCUSSION",
    "ROUND_HR_INTERVIEW",
    "ROUND_ONLINE_ASSESSMENT",
    "ROUND_OTHER",
    "ROUND_TECHNICAL_INTERVIEW",
    "ROUND_TYPES",
    "Skill",
    "Student",
    "StudentSkill",
    "USER_ACTIVE",
    "USER_DISABLED",
    "USER_SUSPENDED",
    "utcnow",
]
