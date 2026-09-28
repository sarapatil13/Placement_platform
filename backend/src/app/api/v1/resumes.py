"""Resume upload, management, and AI-assisted analysis endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import (
    CurrentUser,
    enforce_request_content_length,
    get_actor_context,
    get_current_user,
    get_student_record,
)
from app.core.config import settings
from app.core.errors import ValidationError
from app.core.ratelimit import route_limit
from app.db.models import Resume, Student
from app.db.session import get_db
from app.schemas.resumes import (
    PreparationRoadmap,
    ResumeAnalysisResult,
    ResumeDetail,
    ResumeMetadata,
    ResumeUploadResponse,
    SetPrimaryResume,
)
from app.services import resumes as resume_service

router = APIRouter(prefix="/resumes", tags=["resumes"])


def _to_metadata(r: Resume) -> ResumeMetadata:
    return ResumeMetadata(
        id=r.id,
        filename=r.filename,
        mime_type=r.mime_type,
        size_bytes=r.size_bytes,
        parse_status=r.parse_status,
        is_primary=r.is_primary,
        created_at=r.created_at,
    )


@router.get("", response_model=list[ResumeDetail])
def list_resumes(
    _current: CurrentUser = Depends(get_current_user),
    student: Student = Depends(get_student_record),
    db: Session = Depends(get_db),
) -> list[ResumeDetail]:
    rows = (
        db.query(Resume)
        .filter(Resume.student_id == student.id)
        .order_by(Resume.created_at.desc())
        .all()
    )
    return [
        ResumeDetail(
            id=r.id,
            filename=r.filename,
            mime_type=r.mime_type,
            size_bytes=r.size_bytes,
            parse_status=r.parse_status,
            is_primary=r.is_primary,
            created_at=r.created_at,
            sha256=r.sha256,
            parsed_skills=r.parsed_skills,
            extracted_text=r.extracted_text,
            parse_error=r.parse_error,
        )
        for r in rows
    ]


@router.post("", response_model=ResumeUploadResponse, status_code=201)
@route_limit(settings.rate_limit_upload)
async def upload_resume(
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    student: Student = Depends(get_student_record),
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
) -> ResumeUploadResponse:
    enforce_request_content_length(request, max_bytes=settings.max_upload_bytes)
    content = await file.read()
    if len(content) > settings.max_upload_bytes:
        raise ValidationError("File exceeds the 5MB upload limit.")
    resume = resume_service.upload_resume(
        db,
        student=student,
        filename=file.filename or "resume.pdf",
        content_type=file.content_type or "application/pdf",
        data=content,
        actor_ctx=get_actor_context(request, current),
    )
    return ResumeUploadResponse(
        resume=_to_metadata(resume),
        message="Resume uploaded successfully.",
    )


@router.post("/analyze", response_model=ResumeAnalysisResult)
@route_limit(settings.rate_limit_ai)
def analyze_resume(
    body: dict,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    student: Student = Depends(get_student_record),
    db: Session = Depends(get_db),
) -> ResumeAnalysisResult:
    drive_id = body.get("drive_id") or ""
    resume_id = body.get("resume_id")
    if not drive_id:
        raise ValidationError("drive_id is required for resume-JD analysis.")
    result = resume_service.analyze_resume_against_drive(
        db,
        student=student,
        drive_id=drive_id,
        resume_id=resume_id,
        actor_ctx=get_actor_context(request, current),
    )
    return ResumeAnalysisResult(**result)


@router.post("/{resume_id}/set-primary", response_model=ResumeMetadata)
def set_primary(
    resume_id: str,
    body: SetPrimaryResume | None = None,
    _current: CurrentUser = Depends(get_current_user),
    student: Student = Depends(get_student_record),
    db: Session = Depends(get_db),
) -> ResumeMetadata:
    resume = resume_service.set_primary(db, student=student, resume_id=resume_id)
    return _to_metadata(resume)


@router.delete("/{resume_id}", response_model=dict)
def delete_resume(
    resume_id: str,
    _current: CurrentUser = Depends(get_current_user),
    student: Student = Depends(get_student_record),
    db: Session = Depends(get_db),
) -> dict:
    resume_service.delete_resume(db, student=student, resume_id=resume_id)
    return {"message": "Resume deleted."}


@router.post("/{drive_id}/roadmap", response_model=PreparationRoadmap)
@route_limit(settings.rate_limit_ai)
def prep_roadmap(
    drive_id: str,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    student: Student = Depends(get_student_record),
    db: Session = Depends(get_db),
) -> PreparationRoadmap:
    roadmap = resume_service.build_prep_roadmap(
        db,
        student=student,
        drive_id=drive_id,
        actor_ctx=get_actor_context(request, current),
    )
    return PreparationRoadmap(**roadmap)