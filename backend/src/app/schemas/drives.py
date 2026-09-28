"""Placement drive and eligibility schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EligibilityRuleIn(BaseModel):
    criterion_type: str
    parameters: dict[str, object] = Field(default_factory=dict)

    @field_validator("criterion_type")
    @classmethod
    def _valid_type(cls, v: str) -> str:
        from app.db.models import CRITERIA_CRITERIA_TYPES

        if v not in CRITERIA_CRITERIA_TYPES:
            raise ValueError(f"Unknown criterion type '{v}'.")
        return v


class EligibilityRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    criterion_type: str
    parameters: dict[str, object]
    source: str
    is_active: bool
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    created_at: datetime


class DriveCreate(BaseModel):
    company_id: str
    title: str = Field(min_length=3, max_length=200)
    role_title: str = Field(min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=6000)
    employment_type: str = Field(default="full_time", max_length=50)
    location: str | None = Field(default=None, max_length=150)
    ctc_lpa: str | None = Field(default=None, max_length=50)
    stipend: str | None = Field(default=None, max_length=50)
    apply_by: datetime | None = None
    drive_date: datetime | None = None
    status: str = Field(default="draft", max_length=20)
    criteria: list[EligibilityRuleIn] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v: str) -> str:
        from app.db.models import DRIVE_STATUSES

        if v not in DRIVE_STATUSES:
            raise ValueError(f"Unknown drive status '{v}'.")
        return v

    @model_validator(mode="after")
    def _dates_coherent(self) -> DriveCreate:
        if self.apply_by and self.drive_date and self.apply_by > self.drive_date:
            raise ValueError("apply_by must not be after drive_date.")
        return self


class DriveUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    role_title: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = Field(default=None, max_length=6000)
    employment_type: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=150)
    ctc_lpa: str | None = Field(default=None, max_length=50)
    stipend: str | None = Field(default=None, max_length=50)
    apply_by: datetime | None = None
    drive_date: datetime | None = None
    status: str | None = Field(default=None, max_length=20)
    criteria: list[EligibilityRuleIn] | None = None
    required_skills: list[str] | None = None

    @field_validator("status")
    @classmethod
    def _valid_status(cls, v: str | None) -> str | None:
        from app.db.models import DRIVE_STATUSES

        if v is not None and v not in DRIVE_STATUSES:
            raise ValueError(f"Unknown drive status '{v}'.")
        return v

    @model_validator(mode="after")
    def _dates_coherent(self) -> DriveUpdate:
        if self.apply_by and self.drive_date and self.apply_by > self.drive_date:
            raise ValueError("apply_by must not be after drive_date.")
        return self


class DrivePublishRequest(BaseModel):
    applies_to_all_eligible: bool = False


class DriveRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    company_name: str = ""
    title: str
    role_title: str
    description: str | None = None
    employment_type: str
    location: str | None = None
    ctc_lpa: str | None = None
    stipend: str | None = None
    status: str
    eligibility_confirmed: bool
    is_ai_extraction_pending: bool
    applied_count: int = 0
    published_at: datetime | None = None
    apply_by: datetime | None = None
    drive_date: datetime | None = None
    created_at: datetime
    updated_at: datetime
    criteria: list[EligibilityRuleOut] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)


class PaginatedDrives(BaseModel):
    items: list[DriveRead]
    total: int
    page: int
    limit: int


class DriveEligibilityCheck(BaseModel):
    drive_id: str
    eligible: bool
    score: int
    reason: str
    exact_reasons: list[str]
    failed_rules: list[dict[str, object]]
    passed_rules: list[dict[str, object]]
    evaluated_at: datetime


class EligibilityRuleDetail(BaseModel):
    criterion_type: str
    passed: bool
    detail: str


class EligibilityReport(BaseModel):
    drive_id: str
    student_id: str
    eligible: bool
    overall_reason: str
    rule_results: list[EligibilityRuleDetail]


class BulkEligibilityResult(BaseModel):
    drive_id: str
    total: int
    eligible: int
    ineligible_count: int
    inconclusive: int
    eligible_student_ids: list[str]
    ineligible: list[dict[str, object]]


class JDExtractionSuggestion(BaseModel):
    """AI-extracted JD summary for admin confirmation. Never applied silently."""

    company_name: str | None = None
    role_title: str | None = None
    location: str | None = None
    employment_type: str | None = None
    ctc_lpa: str | None = None
    stipend: str | None = None
    apply_by: datetime | None = None
    drive_date: datetime | None = None
    description_summary: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    suggested_criteria: list[EligibilityRuleIn] = Field(default_factory=list)


class JDUploadResponse(BaseModel):
    drive_id: str
    filename: str
    extracted: JDExtractionSuggestion
    needs_confirmation: bool


class EligibilityCriteriaConfirm(BaseModel):
    criteria: list[EligibilityRuleIn]
    required_skills: list[str] = Field(default_factory=list)