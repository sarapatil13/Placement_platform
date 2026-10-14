"""Placement drive lifecycle: create, update, publish, JD intake, criteria
confirmation, and bulk eligibility evaluation."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError, ValidationError
from app.db.models import (
    DRIVE_DRAFT,
    DRIVE_PUBLISHED,
    AIAnalysis,
    DriveRound,
    DriveSkill,
    EligibilityCriterion,
    PlacementDrive,
    Skill,
    Student,
)
from app.services import ai_service, notifications
from app.services.audit import AuditContext, record
from app.services.documents import (
    DocumentParseError,
    extract_text_from_bytes,
    safe_storage_name,
    sha256_bytes,
)
from app.services.eligibility import evaluate


def get_drive(db: Session, drive_id: str, institution_id: str) -> PlacementDrive:
    drive = db.get(PlacementDrive, drive_id)
    if drive is None or drive.institution_id != institution_id:
        raise NotFoundError("Drive not found.")
    return drive


def create_drive(
    db: Session,
    *,
    institution_id: str,
    company_id: str,
    title: str,
    role_title: str,
    description: str | None,
    employment_type: str,
    location: str | None,
    ctc_lpa: str | None,
    stipend: str | None,
    apply_by: datetime | None,
    drive_date: datetime | None,
    status: str,
    criteria: list[dict],
    required_skills: list[str],
    created_by: str,
    actor_ctx: AuditContext | None = None,
) -> PlacementDrive:
    drive = PlacementDrive(
        institution_id=institution_id,
        company_id=company_id,
        title=title,
        role_title=role_title,
        description=description,
        employment_type=employment_type,
        location=location,
        ctc_lpa=ctc_lpa,
        stipend=stipend,
        status=status,
        apply_by=apply_by,
        drive_date=drive_date,
        created_by=created_by,
        eligibility_confirmed=False,
    )
    db.add(drive)
    db.flush()

    _replace_criteria(db, drive, criteria, actor_ctx=actor_ctx, confirmed=(status != DRIVE_DRAFT))
    _replace_skills(db, institution_id, drive, required_skills)
    record(
        db,
        action="drive.created",
        context=actor_ctx,
        entity_type="drive",
        entity_id=drive.id,
        detail={"title": title, "company_id": company_id},
    )
    db.commit()
    db.refresh(drive)
    return drive


def update_drive(
    db: Session,
    *,
    drive: PlacementDrive,
    values: dict,
    criteria: list[dict] | None = None,
    required_skills: list[str] | None = None,
    actor_ctx: AuditContext | None = None,
) -> PlacementDrive:
    scalar_fields = {
        "title",
        "role_title",
        "description",
        "employment_type",
        "location",
        "ctc_lpa",
        "stipend",
        "apply_by",
        "drive_date",
        "status",
    }
    changes = []
    for key, value in values.items():
        if key in scalar_fields and value is not None:
            old = getattr(drive, key)
            if old != value:
                setattr(drive, key, value)
                changes.append(key)
    if criteria is not None:
        _replace_criteria(db, drive, criteria, actor_ctx=actor_ctx, confirmed=False)
        drive.eligibility_confirmed = False
        changes.append("criteria")
    if required_skills is not None:
        _replace_skills(db, drive.institution_id, drive, required_skills)
        changes.append("skills")
    record(
        db,
        action="drive.updated",
        context=actor_ctx,
        entity_type="drive",
        entity_id=drive.id,
        detail={"changed": changes},
    )
    db.commit()
    db.refresh(drive)
    return drive


def publish_drive(
    db: Session,
    *,
    drive: PlacementDrive,
    criteria: list[dict] | None = None,
    actor_ctx: AuditContext | None = None,
    notify_eligible: bool = True,
) -> PlacementDrive:
    if not drive.eligibility_confirmed:
        drive.eligibility_confirmed = True
        drive.eligibility_confirmed_by = actor_ctx.actor_id if actor_ctx else None
        drive.eligibility_confirmed_at = datetime.now(UTC)
    if criteria is not None:
        _replace_criteria(db, drive, criteria, actor_ctx=actor_ctx, confirmed=True)
        drive.eligibility_confirmed = True
        drive.eligibility_confirmed_by = actor_ctx.actor_id if actor_ctx else None
        drive.eligibility_confirmed_at = datetime.now(UTC)
    drive.status = DRIVE_PUBLISHED
    drive.published_at = drive.published_at or datetime.now(UTC)
    drive.is_ai_extraction_pending = False
    record(
        db,
        action="drive.published",
        context=actor_ctx,
        entity_type="drive",
        entity_id=drive.id,
        detail={"title": drive.title},
    )
    if notify_eligible and actor_ctx:
        _notify_candidates(db, drive)
    db.commit()
    db.refresh(drive)
    return drive


def upload_jd_and_suggest(
    db: Session,
    *,
    drive: PlacementDrive,
    filename: str,
    data: bytes,
    storage,
    actor_ctx: AuditContext | None = None,
) -> dict:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix not in {"pdf", "docx", "txt"}:
        raise ValidationError("JD must be PDF, DOCX, or plain text.")
    if len(data) > settings_max_upload():
        raise ValidationError("JD exceeds the 5MB upload limit.")

    try:
        text = extract_text_from_bytes(data, filename)
    except DocumentParseError as exc:
        raise ValidationError(str(exc)) from exc

    digest = sha256_bytes(data)
    stored = storage.save(
        institution_id=drive.institution_id,
        student_id="_jd",
        filename=f"jd-{drive.id}-{safe_storage_name(filename, digest)}",
        data=data,
    )
    drive.jd_text = text
    drive.jd_filename = filename
    drive.jd_storage_path = str(stored)

    # AI extraction, advisory. Whatever the provider returns is validated into
    # JDExtractionSchema, and the drive is marked "extraction pending".
    try:
        result = ai_service.extract_jd_fields(text)
        raw = result.value.model_dump()
        drive.is_ai_extraction_pending = True
        _persist_jd_analysis(db, drive, result, raw)
        suggestion = raw
    except ai_service.AIError:
        suggestion = {
            "role_title": None,
            "required_skills": [],
            "suggested_min_cgpa": None,
        }
        drive.is_ai_extraction_pending = True

    record(
        db,
        action="jd.uploaded",
        context=actor_ctx,
        entity_type="drive",
        entity_id=drive.id,
        detail={"filename": filename, "characters": len(text)},
    )
    db.commit()
    db.refresh(drive)
    return {"extracted": suggestion, "needs_confirmation": True}


def settings_max_upload() -> int:
    return 5 * 1024 * 1024


def list_rounds(db: Session, *, drive: PlacementDrive) -> list[DriveRound]:
    return (
        db.query(DriveRound)
        .filter(DriveRound.drive_id == drive.id)
        .order_by(DriveRound.position.asc())
        .all()
    )


def replace_rounds(
    db: Session,
    *,
    drive: PlacementDrive,
    rounds: list[dict],
    actor_ctx: AuditContext | None = None,
) -> list[DriveRound]:
    seen_positions: set[int] = set()
    seen: list[DriveRound] = []
    for item in rounds:
        position = int(item["position"])
        if position in seen_positions:
            raise ValidationError(f"Duplicate round position {position}.")
        seen_positions.add(position)
        seen.append(
            DriveRound(
                institution_id=drive.institution_id,
                drive_id=drive.id,
                position=position,
                round_type=item["round_type"],
                title=item["title"],
                topics=[str(t) for t in (item.get("topics") or [])],
                scheduled_at=item.get("scheduled_at"),
            )
        )
    db.query(DriveRound).filter(DriveRound.drive_id == drive.id).delete()
    db.flush()
    db.add_all(seen)
    db.flush()
    record(
        db,
        action="drive.rounds_updated",
        context=actor_ctx,
        entity_type="drive",
        entity_id=drive.id,
        detail={"round_count": len(seen)},
    )
    db.commit()
    db.refresh(drive)
    return seen


def _persist_jd_analysis(db: Session, drive: PlacementDrive, result, raw: dict) -> None:
    db.add(
        AIAnalysis(
            institution_id=drive.institution_id,
            analysis_type="jd_extraction",
            drive_id=drive.id,
            provider=result.provider,
            model=result.model,
            schema_name="JDExtractionSchema",
            result=raw,
            raw_response=result.raw_response,
            status="succeeded",
            latency_ms=result.latency_ms,
            requires_confirmation=True,
        )
    )
    db.flush()


def confirm_extraction(
    db: Session,
    *,
    drive: PlacementDrive,
    criteria: list[dict],
    required_skills: list[str],
    actor_ctx: AuditContext | None = None,
) -> PlacementDrive:
    _replace_criteria(db, drive, criteria, actor_ctx=actor_ctx, confirmed=True)
    _replace_skills(db, drive.institution_id, drive, required_skills)
    drive.is_ai_extraction_pending = False
    drive.eligibility_confirmed = True
    drive.eligibility_confirmed_by = actor_ctx.actor_id if actor_ctx else None
    drive.eligibility_confirmed_at = datetime.now(UTC)
    record(
        db,
        action="jd.confirmed",
        context=actor_ctx,
        entity_type="drive",
        entity_id=drive.id,
        detail={"criteria_count": len(criteria), "skills": len(required_skills)},
    )
    db.commit()
    db.refresh(drive)
    return drive


def _replace_criteria(
    db: Session,
    drive: PlacementDrive,
    criteria: list[dict],
    *,
    actor_ctx: AuditContext | None,
    confirmed: bool,
) -> None:
    seen_types = set()
    seen: list[EligibilityCriterion] = []
    for item in criteria:
        ctype = item.get("criterion_type")
        parameters = item.get("parameters") or {}
        if not ctype:
            raise ValidationError("Each criterion needs a criterion_type.")
        if ctype in seen_types:
            raise ValidationError(f"Duplicate criterion type '{ctype}' for this drive.")
        seen_types.add(ctype)
        row = EligibilityCriterion(
            institution_id=drive.institution_id,
            drive_id=drive.id,
            criterion_type=ctype,
            parameters=parameters,
            source="ai_suggested_confirmed" if confirmed and not _is_manual(actor_ctx, item) else "admin_manual",
            is_active=True,
            confirmed_by=actor_ctx.actor_id if actor_ctx and confirmed else None,
            confirmed_at=datetime.now(UTC) if confirmed else None,
        )
        seen.append(row)
    db.query(EligibilityCriterion).filter(
        EligibilityCriterion.drive_id == drive.id
    ).delete()
    db.flush()
    db.add_all(seen)
    db.flush()


def _is_manual(actor_ctx: AuditContext | None, item: dict) -> bool:
    # Only used to label the source; manual admin entry is the default.
    return item.get("source") != "ai_suggested"


def _replace_skills(db: Session, institution_id: str, drive: PlacementDrive, names: list[str]) -> None:
    db.query(DriveSkill).filter(DriveSkill.drive_id == drive.id).delete()
    db.flush()
    seen = set()
    for name in names or []:
        normalized = " ".join(name.strip().lower().split())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        skill = (
            db.query(Skill)
            .filter(
                Skill.institution_id == institution_id,
                Skill.normalized_name == normalized,
            )
            .first()
        )
        if skill is None:
            skill = Skill(
                institution_id=institution_id,
                name=name.strip(),
                normalized_name=normalized,
            )
            db.add(skill)
            db.flush()
        db.add(
            DriveSkill(
                institution_id=institution_id,
                drive_id=drive.id,
                skill_id=skill.id,
                requirement="required",
                weight=1.0,
            )
        )
    db.flush()


def _notify_candidates(db: Session, drive: PlacementDrive) -> None:
    from app.db.models import User

    result = evaluate_bulk(db, drive=drive)
    eligible_students = result["eligible_students"]
    user_ids = [s.user_id for s in eligible_students]
    users = db.query(User).filter(User.id.in_(user_ids or [""])).all()
    for user in users:
        notifications.create(
            db,
            user_id=user.id,
            institution_id=drive.institution_id,
            type=notifications.NOTIF_NEW_DRIVE,
            title=f"New opportunity: {drive.title}",
            body=f"You are eligible for {drive.title} at {drive.company.name}. Apply before the deadline.",
            link=f"/opportunities/{drive.id}",
            payload={"drive_id": drive.id},
        )
    db.flush()


def evaluate_bulk(
    db: Session, *, drive: PlacementDrive, students: list[Student] | None = None
) -> dict:
    """Evaluate all active students of the institution against the drive.

    Returns a plain dict rather than a model so callers can choose the shape.
    `eligible_students` carries ORM objects for notification fan-out.
    """
    students = students or (
        db.query(Student).filter(
            Student.institution_id == drive.institution_id,
            Student.is_active.is_(True),
        ).all()
    )
    criteria = list(
        db.query(EligibilityCriterion)
        .filter(EligibilityCriterion.drive_id == drive.id)
        .all()
    )
    eligible: list[Student] = []
    ineligible: list[dict] = []
    inconclusive_count = 0
    for student in students:
        verdict = evaluate(
            db, drive_id=drive.id, student=student, criteria=criteria
        )
        if verdict.eligible and verdict.definitive:
            eligible.append(student)
        else:
            ineligible.append(
                {
                    "student_id": student.id,
                    "college_id": student.college_id,
                    "label": verdict.label,
                    "reasons": verdict.reasons[:3],
                }
            )
            if not verdict.definitive:
                inconclusive_count += 1
    return {
        "drive_id": drive.id,
        "total": len(students),
        "eligible": len(eligible),
        "ineligible_count": len(ineligible),
        "inconclusive": inconclusive_count,
        "eligible_students": eligible,
        "eligible_ids": [s.id for s in eligible],
        "ineligible_list": ineligible,
    }