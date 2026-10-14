"""Placement drives: student view + eligibility checks. Admin CRUD lives in
app.api.v1.admin."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import (
    CurrentUser,
    Pagination,
    get_current_user,
    get_pagination,
    get_student_record,
    require_student,
)
from app.core.errors import NotFoundError
from app.db.models import PlacementDrive, Student
from app.db.session import get_db
from app.schemas.drives import (
    DriveEligibilityCheck,
    DriveRead,
    DriveRoundOut,
    EligibilityRuleOut,
    PaginatedDrives,
)
from app.services import drives as drive_service
from app.services.eligibility import evaluate

router = APIRouter(prefix="/drives", tags=["drives"])

_VISIBLE_STATUSES = ["published", "closed"]


def _to_drive_read(drive: PlacementDrive) -> DriveRead:
    criteria = [c for c in drive.criteria if c.is_active]
    return DriveRead(
        id=drive.id,
        company_id=drive.company_id,
        company_name=drive.company.name if drive.company else "",
        title=drive.title,
        role_title=drive.role_title,
        description=drive.description,
        employment_type=drive.employment_type,
        location=drive.location,
        ctc_lpa=drive.ctc_lpa,
        stipend=drive.stipend,
        status=drive.status,
        eligibility_confirmed=drive.eligibility_confirmed,
        is_ai_extraction_pending=drive.is_ai_extraction_pending,
        applied_count=len(drive.applications),
        published_at=drive.published_at,
        apply_by=drive.apply_by,
        drive_date=drive.drive_date,
        created_at=drive.created_at,
        updated_at=drive.updated_at,
criteria=[
            EligibilityRuleOut(
                id=c.id,
                criterion_type=c.criterion_type,
                parameters=c.parameters,
                source=c.source,
                is_active=c.is_active,
                confirmed_by=c.confirmed_by,
                confirmed_at=c.confirmed_at,
                created_at=c.created_at,
            )
            for c in criteria
        ],
        required_skills=[row.skill.name for row in drive.drive_skills],
    )


@router.get("", response_model=PaginatedDrives)
def list_drives(
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
    pagination: Pagination = Depends(get_pagination),
) -> PaginatedDrives:
    q = (
        db.query(PlacementDrive)
        .filter(
            PlacementDrive.institution_id == current.institution_id,
            PlacementDrive.status.in_(_VISIBLE_STATUSES),
        )
    )
    total = q.count()
    rows = q.order_by(PlacementDrive.published_at.desc()).offset(pagination.offset).limit(pagination.limit).all()
    return PaginatedDrives(
        items=[_to_drive_read(d) for d in rows],
        total=total,
        page=pagination.page,
        limit=pagination.limit,
    )


@router.get("/{drive_id}", response_model=DriveRead)
def get_drive(
    drive_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DriveRead:
    drive = drive_service.get_drive(db, drive_id, current.institution_id)
    if drive.status not in _VISIBLE_STATUSES:
        raise NotFoundError("Drive not found.")
    return _to_drive_read(drive)


@router.get("/{drive_id}/rounds", response_model=list[DriveRoundOut])
def list_rounds(
    drive_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DriveRoundOut]:
    drive = drive_service.get_drive(db, drive_id, current.institution_id)
    if drive.status not in _VISIBLE_STATUSES:
        raise NotFoundError("Drive not found.")
    return [
        DriveRoundOut.model_validate(r)
        for r in drive_service.list_rounds(db, drive=drive)
    ]


@router.get("/{drive_id}/eligibility", response_model=DriveEligibilityCheck)
def check_eligibility(
    drive_id: str,
    current: CurrentUser = Depends(require_student),
    db: Session = Depends(get_db),
    student: Student = Depends(get_student_record),
) -> DriveEligibilityCheck:
    drive = drive_service.get_drive(db, drive_id, student.institution_id)
    if drive.status not in _VISIBLE_STATUSES:
        raise NotFoundError("Drive not found.")
    verdict = evaluate(db, drive_id=drive.id, student=student)
    return DriveEligibilityCheck(
        drive_id=drive.id,
        eligible=verdict.eligible,
        score=verdict.score,
        reason=verdict.reasons[0] if verdict.reasons else "No eligibility criteria set.",
        exact_reasons=verdict.reasons,
        failed_rules=verdict.failed_rules,
        passed_rules=verdict.passed_rules,
        evaluated_at=verdict.evaluated_at,
    )
