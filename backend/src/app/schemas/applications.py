"""Application, notification, and analytics schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import APP_APPLIED, APP_TRANSITIONS


class ApplicationCreate(BaseModel):
    drive_id: str
    resume_id: str | None = None
    cover_note: str | None = Field(default=None, max_length=2000)


class ApplicationStatusUpdate(BaseModel):
    new_status: str
    note: str | None = Field(default=None, max_length=500)

    @field_validator("new_status")
    @classmethod
    def _known_status(cls, v: str) -> str:
        if v not in APP_TRANSITIONS and v != APP_APPLIED:
            raise ValueError(f"Unknown application status '{v}'.")
        return v


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    student_id: str
    drive_id: str
    drive_title: str = ""
    company_name: str = ""
    status: str
    eligibility_snapshot: dict[str, object] = Field(default_factory=dict)
    applied_at: datetime
    updated_at: datetime
    cover_note: str | None = None
    withdrawn_reason: str | None = None


class ApplicationDetail(ApplicationRead):
    eligibility_evaluated: bool = True
    resume_filename: str | None = None
    status_history: list[StatusHistoryRow] = Field(default_factory=list)


class StatusHistoryRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    from_status: str | None = None
    to_status: str
    changed_by: str | None = None
    changed_by_role: str | None = None
    note: str | None = None
    is_student_initiated: bool
    created_at: datetime


class PaginatedApplications(BaseModel):
    items: list[ApplicationRead]
    total: int
    page: int
    limit: int


class WithdrawApplicationRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=300)


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    type: str
    title: str
    body: str
    link: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)
    is_read: bool
    created_at: datetime


class PaginatedNotifications(BaseModel):
    items: list[NotificationRead]
    total: int
    page: int
    limit: int
    unread_count: int


class NotificationMarkRead(BaseModel):
    ids: list[str] | None = Field(default=None, description="Empty = all")


class FunnelRow(BaseModel):
    label: str
    count: int


class DepartmentStatRow(BaseModel):
    department_code: str
    department_name: str
    students: int
    applications: int
    placed: int


class StatusStatRow(BaseModel):
    status: str
    count: int


class DriveStatRow(BaseModel):
    drive_id: str
    drive_title: str
    company_name: str
    apps_total: int
    apps_shortlisted: int
    apps_offered: int


class AnalyticsSummary(BaseModel):
    total_students: int
    total_drives: int
    published_drives: int
    total_applications: int
    unique_applicants: int
    applications_per_drive: float
    overall_funnel: list[FunnelRow] = Field(default_factory=list)
    department_stats: list[DepartmentStatRow] = Field(default_factory=list)
    status_stats: list[StatusStatRow] = Field(default_factory=list)
    top_drives: list[DriveStatRow] = Field(default_factory=list)