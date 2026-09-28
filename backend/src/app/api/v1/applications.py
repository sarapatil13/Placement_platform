"""Applications: student create/list/withdraw, admin status updates & reads."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import (
    CurrentUser,
    get_actor_context,
    get_current_user,
    get_student_record,
    require_permission,
)
from app.core.config import settings
from app.core.errors import NotFoundError, PermissionError_
from app.core.ratelimit import route_limit
from app.core.rbac import Permission
from app.db.models import Application, PlacementDrive, Resume, Student
from app.db.session import get_db
from app.schemas.applications import (
    ApplicationCreate,
    ApplicationDetail,
    ApplicationRead,
    ApplicationStatusUpdate,
    StatusHistoryRow,
    WithdrawApplicationRequest,
)
from app.services.applications import ApplicationService

router = APIRouter(prefix="/applications", tags=["applications"])


def _to_read(app: Application) -> ApplicationRead:
    drive = app.drive
    return ApplicationRead(
        id=app.id,
        student_id=app.student_id,
        drive_id=app.drive_id,
        drive_title=drive.title if drive else "",
        company_name=drive.company.name if drive and drive.company else "",
        status=app.status,
        eligibility_snapshot=app.eligibility_snapshot or {},
        applied_at=app.applied_at,
        updated_at=app.updated_at,
        cover_note=app.cover_note,
        withdrawn_reason=app.withdrawn_reason,
    )


def _to_detail(app: Application) -> ApplicationDetail:
    base = _to_read(app)
    return ApplicationDetail(
        **base.model_dump(),
        resume_filename=(
            db_get_resume_filename(app.resume_id) if app.resume_id else None
        ),
        status_history=[
            StatusHistoryRow(
                id=h.id,
                from_status=h.from_status,
                to_status=h.to_status,
                changed_by=h.changed_by,
                changed_by_role=h.changed_by_role,
                note=h.note,
                is_student_initiated=h.is_student_initiated,
                created_at=h.created_at,
            )
            for h in app.status_history
        ],
    )


def db_get_resume_filename(resume_id: str) -> str | None:
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        r = db.get(Resume, resume_id)
        return r.filename if r else None


@router.get("/me", response_model=list[ApplicationRead])
def my_applications(
    _current: CurrentUser = Depends(get_current_user),
    student: Student = Depends(get_student_record),
) -> list[ApplicationRead]:
    return [_to_read(a) for a in student.applications]


@router.post("", response_model=ApplicationRead, status_code=201)
@route_limit(settings.rate_limit_write)
def apply_to_drive(
    body: ApplicationCreate,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    student: Student = Depends(get_student_record),
    db: Session = Depends(get_db),
) -> ApplicationRead:
    resume_text = None
    if body.resume_id:
        resume = db.get(Resume, body.resume_id)
        if resume is None or resume.student_id != student.id:
            from app.core.errors import NotFoundError

            raise NotFoundError("Resume not found.")
        resume_text = resume.extracted_text
    service = ApplicationService(db, actor_ctx=get_actor_context(request, current))
    app = service.create(
        student=student,
        drive_id=body.drive_id,
        resume_id=body.resume_id,
        cover_note=body.cover_note,
        resume_snapshot_text=resume_text,
    )
    from app.db.models import Notification  # noqa: F401
    from app.services import notifications

    drive = db.get(PlacementDrive, body.drive_id)
    if drive:
        notifications.create(
            db,
            user_id=current.user_id,
            institution_id=current.institution_id,
            type=notifications.NOTIF_APPLICATION,
            title=f"Application submitted: {drive.title}",
            body="Your application was accepted and is now under review.",
            link=f"/applications/{app.id}",
            payload={"application_id": app.id, "drive_id": drive.id},
        )
    return _to_read(app)


@router.get("/{application_id}", response_model=ApplicationDetail)
def get_application(
    application_id: str,
    current: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApplicationDetail:
    app = db.get(Application, application_id)
    if app is None:
        raise NotFoundError("Application not found.")
    if current.role in {"placement_admin", "super_admin"}:
        # Admins may inspect applications within their own institution only.
        if app.institution_id != current.institution_id:
            raise NotFoundError("Application not found.")
    else:
        # Students can only ever see their own applications.
        student = db.query(Student).filter(Student.user_id == current.user_id).first()
        if student is None or app.student_id != student.id:
            raise PermissionError_("You can only view your own applications.")
        if app.institution_id != current.institution_id:
            raise NotFoundError("Application not found.")
    return _to_detail(app)


@router.post("/{application_id}/withdraw", response_model=ApplicationRead)
@route_limit(settings.rate_limit_write)
def withdraw(
    application_id: str,
    body: WithdrawApplicationRequest,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    student: Student = Depends(get_student_record),
    db: Session = Depends(get_db),
) -> ApplicationRead:
    service = ApplicationService(db, actor_ctx=get_actor_context(request, current))
    app = service.withdraw(
        application_id, student_id=student.id, reason=body.reason
    )
    return _to_read(app)


# --------------------------------------------------------------------------- #
# Admin operations (RBAC-gated)
# --------------------------------------------------------------------------- #
@router.patch("/{application_id}/status", response_model=ApplicationRead)
def update_status(
    application_id: str,
    body: ApplicationStatusUpdate,
    request: Request,
    current: CurrentUser = Depends(require_permission(Permission.UPDATE_APPLICATION_STATUS)),
    db: Session = Depends(get_db),
) -> ApplicationRead:
    service = ApplicationService(db, actor_ctx=get_actor_context(request, current))
    app = service.change_status(application_id, body.new_status, body.note)
    return _to_read(app)


@router.get("/drive/{drive_id}", response_model=list[ApplicationRead])
def list_for_drive(
    drive_id: str,
    current: CurrentUser = Depends(require_permission(Permission.READ_ALL_APPLICATIONS)),
    db: Session = Depends(get_db),
) -> list[ApplicationRead]:
    apps = db.query(Application).filter(
        Application.drive_id == drive_id,
        Application.institution_id == current.institution_id,
    )
    return [_to_read(a) for a in apps.all()]