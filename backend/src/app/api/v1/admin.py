"""Admin endpoints (placement cell): imports, institutional data, drives,
companies, JD confirmation, eligibility, analytics, audit."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.api.deps import (
    CurrentUser,
    Pagination,
    enforce_request_content_length,
    get_actor_context,
    get_pagination,
    require_permission,
)
from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.ratelimit import route_limit
from app.core.rbac import Permission
from app.db.models import (
    Application,
    Company,
    PlacementDrive,
    Student,
    User,
)
from app.db.session import get_db
from app.schemas.applications import (
    ApplicationRead,
    ApplicationStatusUpdate,
    PaginatedApplications,
)
from app.schemas.companies import (
    CompanyCreate,
    CompanyRead,
    CompanyUpdate,
    PaginatedCompanies,
)
from app.schemas.students import (
    InstitutionalStudentUpdate,
    PaginatedStudents,
    StudentBrief,
    StudentImportRequest,
    StudentImportResult,
)
from app.services import drives as drive_service
from app.services import students as student_service
from app.services.applications import ApplicationService
from app.services.audit import record

router = APIRouter(prefix="/admin", tags=["admin"])


# --------------------------------------------------------------------------- #
# Students
# --------------------------------------------------------------------------- #
@router.post("/students/import", response_model=StudentImportResult)
def import_students(
    body: StudentImportRequest,
    request: Request,
    current: CurrentUser = Depends(require_permission(Permission.IMPORT_STUDENTS)),
    db: Session = Depends(get_db),
) -> StudentImportResult:
    actor = get_actor_context(request, current)
    created = skipped = 0
    failed: list[dict[str, str]] = []
    activation_tokens: list[dict[str, str]] = []
    if len(body.students) > settings.max_import_rows:
        raise ValidationError(
            f"Bulk import is limited to {settings.max_import_rows} students per request."
        )
    for row in body.students:
        try:
            user, _student, token = student_service.provision_student(
                db,
                institution_id=current.institution_id,
                college_id=row.college_id,
                email=str(row.email),
                full_name=row.full_name,
                department_code=row.department_code,
                batch_year=row.batch_year,
                cgpa=row.cgpa,
                backlog_count=row.backlog_count,
                active_backlogs=row.active_backlogs,
                gender=row.gender,
                date_of_birth=row.date_of_birth,
                phone=row.phone,
                academic_data_verified=row.academic_data_verified,
                actor_ctx=actor,
                send_activation=body.send_activation,
            )
            created += 1
            if token:
                activation_tokens.append({"email": user.email, "token": token})
        except ConflictError as exc:
            skipped += 1
            failed.append({"row": row.college_id, "reason": exc.detail})
    record(
        db,
        action="student.bulk_import",
        context=actor,
        entity_type="student",
        outcome="success",
        detail={"created": created, "skipped": skipped, "failed": len(failed)},
    )
    db.commit()
    return StudentImportResult(
        created=created,
        skipped=skipped,
        failed=failed,
        activation_tokens=activation_tokens,
    )


@router.get("/students", response_model=PaginatedStudents)
def list_students(
    current: CurrentUser = Depends(require_permission(Permission.READ_ANY_STUDENT)),
    db: Session = Depends(get_db),
    pagination: Pagination = Depends(get_pagination),
    department: str | None = None,
    batch: int | None = None,
    q: str | None = None,
) -> PaginatedStudents:
    query = db.query(Student).filter(Student.institution_id == current.institution_id)
    if department:
        query = query.join(Student.department).filter(
            __import__("app.db.models", fromlist=["Department"]).Department.code == department.upper()
        )
    if batch:
        query = query.filter(Student.batch_year == batch)
    if q:
        like = f"%{q}%"
        query = query.filter(
            (Student.college_id.ilike(like))
            | (Student.user.has(User.full_name.ilike(like)))
            | (Student.user.has(User.email.ilike(like)))
        )
    total = query.count()
    rows = query.order_by(Student.batch_year.desc(), Student.college_id).offset(pagination.offset).limit(pagination.limit).all()
    return PaginatedStudents(
        items=[_to_brief(s) for s in rows],
        total=total,
        page=pagination.page,
        limit=pagination.limit,
    )


def _to_brief(student: Student) -> StudentBrief:
    user = student.user
    dept = student.department
    return StudentBrief(
        id=student.id,
        user_id=student.user_id,
        college_id=student.college_id,
        full_name=user.full_name if user else "",
        email=user.email if user else "",
        batch_year=student.batch_year,
        department_code=dept.code if dept else "",
        department_name=dept.name if dept else "",
        cgpa=student.cgpa,
        backlog_count=student.backlog_count,
        active_backlogs=student.active_backlogs,
        academic_data_verified=student.academic_data_verified,
        is_active=student.is_active,
    )


@router.get("/students/{student_id}", response_model=StudentBrief)
def get_student(
    student_id: str,
    current: CurrentUser = Depends(require_permission(Permission.READ_ANY_STUDENT)),
    db: Session = Depends(get_db),
) -> StudentBrief:
    student = _scoped_student(db, student_id, current.institution_id)
    return _to_brief(student)


@router.patch("/students/{student_id}", response_model=StudentBrief)
def update_student_institutional(
    student_id: str,
    body: InstitutionalStudentUpdate,
    request: Request,
    current: CurrentUser = Depends(
        require_permission(Permission.UPDATE_INSTITUTIONAL_STUDENT_FIELDS)
    ),
    db: Session = Depends(get_db),
) -> StudentBrief:
    student = _scoped_student(db, student_id, current.institution_id)
    updated = student_service.update_institutional_fields(
        db,
        student=student,
        institution_id=current.institution_id,
        values=body.model_dump(exclude_unset=True),
        actor_ctx=get_actor_context(request, current),
    )
    return _to_brief(updated)


def _scoped_student(db: Session, student_id: str, institution_id: str) -> Student:
    student = db.get(Student, student_id)
    if student is None or student.institution_id != institution_id:
        raise NotFoundError("Student not found.")
    return student


# --------------------------------------------------------------------------- #
# Companies
# --------------------------------------------------------------------------- #
def _company_read(company: Company) -> CompanyRead:
    return CompanyRead(
        id=company.id,
        name=company.name,
        website=company.website,
        industry=company.industry,
        about=company.about,
        location=company.location,
        contact_email=company.contact_email,
        contact_name=company.contact_name,
        tiers=company.tiers or [],
        reputation_score=company.reputation_score,
        is_active=company.is_active,
        created_at=company.created_at,
    )


@router.get("/companies", response_model=PaginatedCompanies)
def list_companies(
    current: CurrentUser = Depends(require_permission(Permission.MANAGE_COMPANIES)),
    db: Session = Depends(get_db),
    pagination: Pagination = Depends(get_pagination),
) -> PaginatedCompanies:
    q = db.query(Company).filter(Company.institution_id == current.institution_id)
    total = q.count()
    rows = q.order_by(Company.name).offset(pagination.offset).limit(pagination.limit).all()
    return PaginatedCompanies(
        items=[_company_read(c) for c in rows],
        total=total,
        page=pagination.page,
        limit=pagination.limit,
    )


@router.post("/companies", response_model=CompanyRead)
def create_company(
    body: CompanyCreate,
    request: Request,
    current: CurrentUser = Depends(require_permission(Permission.MANAGE_COMPANIES)),
    db: Session = Depends(get_db),
) -> CompanyRead:
    existing = db.query(Company).filter(
        Company.institution_id == current.institution_id,
        Company.name == body.name,
    ).first()
    if existing:
        raise ConflictError("A company with this name already exists.")
    company = Company(institution_id=current.institution_id, **body.model_dump())
    db.add(company)
    record(
        db,
        action="company.created",
        context=get_actor_context(request, current),
        entity_type="company",
        entity_id=company.id,
        detail={"name": company.name},
    )
    db.commit()
    db.refresh(company)
    return _company_read(company)


@router.patch("/companies/{company_id}", response_model=CompanyRead)
def update_company(
    company_id: str,
    body: CompanyUpdate,
    request: Request,
    current: CurrentUser = Depends(require_permission(Permission.MANAGE_COMPANIES)),
    db: Session = Depends(get_db),
) -> CompanyRead:
    company = db.get(Company, company_id)
    if company is None or company.institution_id != current.institution_id:
        raise NotFoundError("Company not found.")
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(company, key, value)
    record(
        db,
        action="company.updated",
        context=get_actor_context(request, current),
        entity_type="company",
        entity_id=company.id,
    )
    db.commit()
    db.refresh(company)
    return _company_read(company)


# --------------------------------------------------------------------------- #
# Drive management (includes JD upload + confirmation)
# --------------------------------------------------------------------------- #
@router.get("/drives", response_model=list)
def list_admin_drives(
    current: CurrentUser = Depends(require_permission(Permission.MANAGE_DRIVES)),
    db: Session = Depends(get_db),
) -> list:
    rows = (
        db.query(PlacementDrive)
        .filter(PlacementDrive.institution_id == current.institution_id)
        .order_by(PlacementDrive.created_at.desc())
        .all()
    )
    return [
        {
            "id": d.id,
            "title": d.title,
            "company_name": d.company.name if d.company else "",
            "status": d.status,
            "eligibility_confirmed": d.eligibility_confirmed,
            "is_ai_extraction_pending": d.is_ai_extraction_pending,
            "applied_count": len(d.applications),
            "created_at": d.created_at,
        }
        for d in rows
    ]


@router.post("/drives", response_model=dict)
def create_drive(
    body: dict,
    request: Request,
    current: CurrentUser = Depends(require_permission(Permission.MANAGE_DRIVES)),
    db: Session = Depends(get_db),
) -> dict:
    _validate_drive_payload(body)
    drive = drive_service.create_drive(
        db,
        institution_id=current.institution_id,
        company_id=body["company_id"],
        title=body["title"],
        role_title=body.get("role_title") or body["title"],
        description=body.get("description"),
        employment_type=body.get("employment_type", "full_time"),
        location=body.get("location"),
        ctc_lpa=body.get("ctc_lpa"),
        stipend=body.get("stipend"),
        apply_by=_dt(body.get("apply_by")),
        drive_date=_dt(body.get("drive_date")),
        status=body.get("status", "draft"),
        criteria=body.get("criteria", []),
        required_skills=body.get("required_skills", []),
        created_by=current.user_id,
        actor_ctx=get_actor_context(request, current),
    )
    return {"id": drive.id, "status": drive.status}


@router.patch("/drives/{drive_id}", response_model=dict)
def update_drive(
    drive_id: str,
    body: dict,
    request: Request,
    current: CurrentUser = Depends(require_permission(Permission.MANAGE_DRIVES)),
    db: Session = Depends(get_db),
) -> dict:
    drive = drive_service.get_drive(db, drive_id, current.institution_id)
    values = {
        k: v
        for k, v in body.items()
        if k
        in {
            "title", "role_title", "description", "employment_type", "location",
            "ctc_lpa", "stipend", "apply_by", "drive_date", "status",
        }
    }
    for key in ("apply_by", "drive_date"):
        if key in values:
            values[key] = _dt(values[key])
    drive_service.update_drive(
        db,
        drive=drive,
        values=values,
        criteria=body.get("criteria"),
        required_skills=body.get("required_skills"),
        actor_ctx=get_actor_context(request, current),
    )
    return {"id": drive.id, "status": drive.status}


@router.post("/drives/{drive_id}/publish", response_model=dict)
def publish_drive(
    drive_id: str,
    body: dict,
    request: Request,
    current: CurrentUser = Depends(require_permission(Permission.PUBLISH_DRIVE)),
    db: Session = Depends(get_db),
) -> dict:
    drive = drive_service.get_drive(db, drive_id, current.institution_id)
    criteria = body.get("criteria")
    drive_service.publish_drive(
        db,
        drive=drive,
        criteria=criteria,
        actor_ctx=get_actor_context(request, current),
    )
    return {"id": drive.id, "status": drive.status, "notified": True}


@router.post("/drives/{drive_id}/jd", response_model=dict)
@route_limit(settings.rate_limit_upload)
async def upload_jd(
    drive_id: str,
    request: Request,
    current: CurrentUser = Depends(require_permission(Permission.UPLOAD_JD)),
    db: Session = Depends(get_db),
) -> dict:
    drive = drive_service.get_drive(db, drive_id, current.institution_id)
    enforce_request_content_length(request, max_bytes=settings.max_upload_bytes)
    form = await request.form()
    file_part = form.get("file")
    if not isinstance(file_part, UploadFile):
        raise ValidationError("A 'file' part is required.")
    file = file_part
    data = await file.read()
    result = drive_service.upload_jd_and_suggest(
        db,
        drive=drive,
        filename=file.filename or "jd.txt",
        data=data,
        storage=__import__("app.services.resumes", fromlist=["ResumeStorage"]).ResumeStorage(),
        actor_ctx=get_actor_context(request, current),
    )
    return {"drive_id": drive.id, "filename": file.filename, **result}


@router.post("/drives/{drive_id}/jd/confirm", response_model=dict)
async def confirm_jd(
    drive_id: str,
    request: Request,
    current: CurrentUser = Depends(
        require_permission(Permission.CONFIRM_AI_EXTRACTION)
    ),
    db: Session = Depends(get_db),
    body: dict | None = None,
) -> dict:
    drive = drive_service.get_drive(db, drive_id, current.institution_id)
    body = body or {}
    criteria = body.get("criteria", [])
    required_skills = body.get("required_skills", [])
    _validate_criteria(criteria)
    drive_service.confirm_extraction(
        db,
        drive=drive,
        criteria=criteria,
        required_skills=required_skills,
        actor_ctx=get_actor_context(request, current),
    )
    return {"drive_id": drive.id, "confirmed": True}


@router.post("/drives/{drive_id}/eligibility/evaluate", response_model=dict)
def evaluate_drive(
    drive_id: str,
    current: CurrentUser = Depends(require_permission(Permission.MANAGE_ELIGIBILITY_CRITERIA)),
    db: Session = Depends(get_db),
) -> dict:
    drive = drive_service.get_drive(db, drive_id, current.institution_id)
    result = drive_service.evaluate_bulk(db, drive=drive)
    return {
        "drive_id": drive.id,
        "total": result["total"],
        "eligible": result["eligible"],
        "ineligible_count": result["ineligible_count"],
        "inconclusive": result["inconclusive"],
        "eligible_ids": result["eligible_ids"],
        "ineligible": result["ineligible_list"],
    }


# --------------------------------------------------------------------------- #
# Applications under admin
# --------------------------------------------------------------------------- #
@router.get("/applications", response_model=PaginatedApplications)
def list_all_applications(
    current: CurrentUser = Depends(require_permission(Permission.READ_ALL_APPLICATIONS)),
    db: Session = Depends(get_db),
    pagination: Pagination = Depends(get_pagination),
    drive_id: str | None = None,
    status: str | None = None,
    department: str | None = None,
) -> PaginatedApplications:
    q = db.query(Application).filter(Application.institution_id == current.institution_id)
    if drive_id:
        q = q.filter(Application.drive_id == drive_id)
    if status:
        q = q.filter(Application.status == status)
    if department:
        sub = db.query(Student.id).join(Student.department).filter(
            __import__("app.db.models", fromlist=["Department"]).Department.code == department.upper()
        )
        q = q.filter(Application.student_id.in_(sub))
    total = q.count()
    rows = (
        q.order_by(Application.applied_at.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )
    return PaginatedApplications(
        items=[_app_read(a) for a in rows],
        total=total,
        page=pagination.page,
        limit=pagination.limit,
    )


@router.patch("/applications/{application_id}/status", response_model=dict)
def admin_set_status(
    application_id: str,
    body: ApplicationStatusUpdate,
    request: Request,
    current: CurrentUser = Depends(
        require_permission(Permission.UPDATE_APPLICATION_STATUS)
    ),
    db: Session = Depends(get_db),
) -> dict:
    app = db.get(Application, application_id)
    if app is None or app.institution_id != current.institution_id:
        raise NotFoundError("Application not found.")
    service = ApplicationService(db, actor_ctx=get_actor_context(request, current))
    updated = service.change_status(application_id, body.new_status, body.note)
    return {"id": updated.id, "status": updated.status}


# --------------------------------------------------------------------------- #
# Analytics + audit
# --------------------------------------------------------------------------- #
@router.get("/analytics/summary", response_model=dict)
def analytics_summary(
    current: CurrentUser = Depends(require_permission(Permission.READ_ANALYTICS)),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.analytics import summary

    return summary(db, institution_id=current.institution_id)


@router.get("/analytics/funnel", response_model=dict)
def analytics_funnel(
    current: CurrentUser = Depends(require_permission(Permission.READ_ANALYTICS)),
    db: Session = Depends(get_db),
) -> dict:
    from app.services.analytics import _overall_funnel

    return {"funnel": _overall_funnel(db, current.institution_id)}


@router.get("/audit-log", response_model=dict)
def audit_log(
    current: CurrentUser = Depends(require_permission(Permission.READ_AUDIT_LOG)),
    db: Session = Depends(get_db),
    pagination: Pagination = Depends(get_pagination),
    action: str | None = None,
    actor: str | None = None,
) -> dict:
    from app.db.models import AuditLog

    q = db.query(AuditLog).filter(
        AuditLog.institution_id == current.institution_id
    )
    if action:
        q = q.filter(AuditLog.action == action)
    if actor:
        q = q.filter(AuditLog.actor_email == actor)
    total = q.count()
    rows = (
        q.order_by(AuditLog.created_at.desc())
        .offset(pagination.offset)
        .limit(pagination.limit)
        .all()
    )
    return {
        "items": [
            {
                "id": r.id,
                "actor_email": r.actor_email,
                "actor_role": r.actor_role,
                "action": r.action,
                "entity_type": r.entity_type,
                "entity_id": r.entity_id,
                "outcome": r.outcome,
                "ip_address": r.ip_address,
                "detail": r.detail,
                "created_at": r.created_at,
            }
            for r in rows
        ],
        "total": total,
        "page": pagination.page,
        "limit": pagination.limit,
    }


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _validate_drive_payload(body: dict) -> None:
    if not body.get("company_id") or not body.get("title"):
        raise ValidationError("company_id and title are required.")
    _validate_criteria(body.get("criteria", []))


def _validate_criteria(criteria: list) -> None:
    for c in criteria:
        if not c.get("criterion_type"):
            raise ValidationError("Each criterion needs a criterion_type.")


def _dt(value) -> datetime | None:
    from datetime import datetime

    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValidationError(f"Invalid datetime value: {value}") from exc


def _app_read(app: Application) -> ApplicationRead:
    from app.api.v1.applications import _to_read

    return _to_read(app)