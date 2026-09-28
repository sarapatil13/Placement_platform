"""Student, department, and user-import schemas."""

from __future__ import annotations

import re
from datetime import date

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.config import settings

_INPUT_RE = re.compile(r"\s+")

_EDITABLE_CONTACT_FIELDS = {
    "phone",
    "profile_headline",
    "about",
    "portfolio_url",
    "linkedin_url",
    "github_url",
    "location",
    "resume_headline",
}


class DepartmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    code: str
    name: str
    degree: str | None = None
    is_technical: bool


class DepartmentCreate(BaseModel):
    code: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=2, max_length=150)
    degree: str | None = Field(default=None, max_length=100)
    is_technical: bool = True

    @field_validator("code")
    @classmethod
    def _upper_code(cls, v: str) -> str:
        return v.strip().upper()


class DepartmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    degree: str | None = Field(default=None, max_length=100)
    is_technical: bool | None = None


class StudentSelfUpdate(BaseModel):
    """Fields a student is permitted to change. Anything else is rejected."""

    phone: str | None = Field(default=None, max_length=32)
    profile_headline: str | None = Field(default=None, max_length=200)
    about: str | None = Field(default=None, max_length=4000)
    portfolio_url: str | None = Field(default=None, max_length=400)
    linkedin_url: str | None = Field(default=None, max_length=400)
    github_url: str | None = Field(default=None, max_length=400)
    location: str | None = Field(default=None, max_length=120)
    resume_headline: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _reject_authoritative_fields(self) -> StudentSelfUpdate:
        got = self.model_dump(exclude_unset=True)
        unexpected = set(got) - _EDITABLE_CONTACT_FIELDS
        if unexpected:
            raise ValueError(
                "Students cannot modify institution-owned fields: "
                + ", ".join(sorted(unexpected))
            )
        return self


class InstitutionalStudentUpdate(BaseModel):
    """Placement-cell update of authoritative academic data."""

    college_id: str | None = Field(default=None, min_length=3, max_length=50)
    department_code: str | None = None
    batch_year: int | None = Field(default=None, ge=2000, le=2100)
    cgpa: float | None = Field(default=None, ge=0, le=10)
    cgpa_source: str | None = Field(default=None, max_length=60)
    backlog_count: int | None = Field(default=None, ge=0, le=200)
    active_backlogs: int | None = Field(default=None, ge=0, le=200)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, max_length=20)
    academic_data_verified: bool | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def _coerce_cgpa(self) -> InstitutionalStudentUpdate:
        if self.cgpa is not None and self.cgpa > settings.institution.grading_scale_max:
            raise ValueError(
                f"CGPA cannot exceed the institution scale "
                f"({settings.institution.grading_scale_max})."
            )
        # Setting cgpa to None explicitly is how the cell flags "missing data".
        return self


class StudentImportRow(BaseModel):
    college_id: str = Field(min_length=3, max_length=50)
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=150)
    department_code: str = Field(min_length=2, max_length=20)
    batch_year: int = Field(ge=2000, le=2100)
    cgpa: float | None = Field(default=None, ge=0, le=10)
    backlog_count: int = Field(default=0, ge=0, le=200)
    active_backlogs: int = Field(default=0, ge=0, le=200)
    gender: str | None = Field(default=None, max_length=20)
    date_of_birth: date | None = None
    phone: str | None = Field(default=None, max_length=32)
    academic_data_verified: bool = True

    @field_validator("college_id")
    @classmethod
    def _up_college_id(cls, v: str) -> str:
        return v.strip().upper()


class StudentImportRequest(BaseModel):
    students: list[StudentImportRow] = Field(min_length=1, max_length=500)
    send_activation: bool = True


class StudentImportResult(BaseModel):
    created: int
    skipped: int
    failed: list[dict[str, str]]
    activation_tokens: list[dict[str, str]]


class StudentBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    user_id: str
    college_id: str
    full_name: str
    email: EmailStr
    batch_year: int
    department_code: str
    department_name: str
    cgpa: float | None
    backlog_count: int | None
    active_backlogs: int | None
    academic_data_verified: bool
    is_active: bool


class StudentDetail(StudentBrief):
    profile_headline: str | None = None
    about: str | None = None
    phone: str | None = None
    location: str | None = None
    portfolio_url: str | None = None
    linkedin_url: str | None = None
    github_url: str | None = None
    gender: str | None = None
    date_of_birth: date | None = None


class SkillRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    normalized_name: str
    category: str | None = None
    proficiency: int | None = None
    years_experience: float | None = None
    source: str | None = None
    is_verified: bool = False


class SkillUpsert(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    proficiency: int | None = Field(default=None, ge=1, le=5)
    years_experience: float | None = Field(default=None, ge=0, le=40)

    @field_validator("name")
    @classmethod
    def _norm(cls, v: str) -> str:
        return _INPUT_RE.sub(" ", v.strip())


class PaginatedStudents(BaseModel):
    items: list[StudentBrief]
    total: int
    page: int
    limit: int