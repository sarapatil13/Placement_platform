"""Resume schemas plus resume/JD analysis outputs and AI structured schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ResumeMetadata(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    mime_type: str
    size_bytes: int
    parse_status: str
    is_primary: bool
    created_at: datetime


class ResumeUploadResponse(BaseModel):
    resume: ResumeMetadata
    message: str


class ResumeDetail(ResumeMetadata):
    sha256: str
    parsed_skills: list[str] = Field(default_factory=list)
    extracted_text: str | None = None
    parse_error: str | None = None


class SetPrimaryResume(BaseModel):
    resume_id: str


class ResumeAnalysisResult(BaseModel):
    """Validated AI resume-JD match. Deterministic scoring is always computed
    server-side; AI may *inform* the skill list but never the outcome."""

    skill_match: float
    matched_skills: list[str] = Field(default_factory=list)
    partial_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    resume_skills_detected: list[str] = Field(default_factory=list)
    drive_required_skills: list[str] = Field(default_factory=list)
    skill_gap_analysis: list[dict[str, str]] = Field(default_factory=list)
    feedback_text: str | None = None
    summary: str | None = None
    analyzed_at: datetime


class SkillGapItem(BaseModel):
    skill: str
    status: str  # matched | partial | missing
    recommendation: str


class PreparationRoadmap(BaseModel):
    drive_id: str
    skill_gaps: list[SkillGapItem] = Field(default_factory=list)
    roadmap_steps: list[str] = Field(default_factory=list)
    suggested_practice: list[str] = Field(default_factory=list)
    disclaimer: str


class SuggestedCriterion(BaseModel):
    criterion_type: str
    parameters: dict[str, object] = Field(default_factory=dict)
    rationale: str | None = None


class JDExtractionResult(BaseModel):
    """Structured output from AI-driven JD extraction. Admin confirms before use."""

    role_title: str | None = None
    location: str | None = None
    employment_type: str | None = None
    ctc_lpa: str | None = None
    stipend: str | None = None
    apply_by: datetime | None = None
    drive_date: datetime | None = None
    description_summary: str | None = None
    required_skills: list[str] = Field(default_factory=list)
    suggested_package: str | None = None
    suggested_criteria: list[SuggestedCriterion] = Field(default_factory=list)


class Announcement(BaseModel):
    drive_id: str
    title: str
    body: str
    recipients: str  # all | eligible | department:<code> | student:<id>


class AuditRow(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    actor_id: str | None = None
    actor_email: str | None = None
    actor_role: str | None = None
    action: str
    entity_type: str | None = None
    entity_id: str | None = None
    outcome: str
    ip_address: str | None = None
    detail: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class PaginatedAudit(BaseModel):
    items: list[AuditRow]
    total: int
    page: int
    limit: int