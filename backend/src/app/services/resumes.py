"""Resume storage, parsing, and AI-assisted analysis.

Files are stored under `UPLOAD_DIR/<institution_id>/<student_id>/` with a
sha256-prefixed name; the extension is whitelisted. Raw text and extracted
skills are persisted on the Resume row. AI analysis is carried on AIAnalysis rows
and the validated result is exposed through the API; a provider failure returns
a deterministic fallback (never 5xx).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import NotFoundError, ValidationError
from app.db.models import AIAnalysis, DriveSkill, PlacementDrive, Resume, Student
from app.services import ai_service
from app.services.audit import AuditContext, record
from app.services.documents import (
    DocumentParseError,
    extract_text_from_bytes,
    safe_storage_name,
    sha256_bytes,
)
from app.services.skill_matching import match_skills

MAX_RESUMES_PER_STUDENT = 10


class ResumeStorage:
    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or settings.upload_dir

    def root_for(self, institution_id: str, student_id: str) -> Path:
        root = self.base_dir / institution_id / student_id
        root.mkdir(parents=True, exist_ok=True)
        return root

    def save(self, *, institution_id: str, student_id: str, filename: str, data: bytes) -> Path:
        digest = sha256_bytes(data)
        storage_name = safe_storage_name(filename, digest)
        dest = self.root_for(institution_id, student_id) / storage_name
        if dest.exists():
            return dest
        dest.write_bytes(data)
        return dest


def upload_resume(
    db: Session,
    *,
    student: Student,
    filename: str,
    content_type: str,
    data: bytes,
    make_primary: bool = True,
    storage: ResumeStorage | None = None,
    actor_ctx: AuditContext | None = None,
) -> Resume:
    _validate_upload(filename, content_type, data)
    storage = storage or ResumeStorage()

    count = db.query(Resume).filter(Resume.student_id == student.id).count()
    if count >= MAX_RESUMES_PER_STUDENT:
        raise ValidationError(f"You can keep at most {MAX_RESUMES_PER_STUDENT} resumes.")

    path = storage.save(
        institution_id=student.institution_id,
        student_id=student.id,
        filename=filename,
        data=data,
    )

    parsed_skills: list[str] = []
    parse_status = "pending"
    parse_error: str | None = None
    extracted: str | None = None
    try:
        extracted = extract_text_from_bytes(data, filename)
        parse_status = "parsed"
        parsed_skills = _detect_skills(extracted)
    except DocumentParseError as exc:
        parse_status = "failed"
        parse_error = str(exc.detail)

    resume = Resume(
        institution_id=student.institution_id,
        student_id=student.id,
        filename=filename,
        storage_path=str(path),
        mime_type=content_type or "application/octet-stream",
        size_bytes=len(data),
        sha256=sha256_bytes(data),
        extracted_text=extracted,
        parse_status=parse_status,
        parse_error=parse_error,
        is_primary=make_primary if count == 0 else False,
        parsed_skills=parsed_skills,
    )
    db.add(resume)
    if (make_primary or count == 0):
        db.query(Resume).filter(
            Resume.student_id == student.id, Resume.id != resume.id
        ).update({"is_primary": False})
        resume.is_primary = True
    db.flush()
    record(
        db,
        action="resume.uploaded",
        context=actor_ctx,
        entity_type="resume",
        entity_id=resume.id,
        detail={"filename": filename, "size": len(data), "parse_status": parse_status},
    )
    db.commit()
    db.refresh(resume)
    return resume


def _validate_upload(filename: str, content_type: str, data: bytes) -> None:
    if len(data) > settings.max_upload_bytes:
        raise ValidationError(
            f"File exceeds the {settings.max_upload_bytes // (1024 * 1024)}MB upload limit."
        )
    suffix = Path(filename).suffix.lower() or ""
    if suffix not in settings.allowed_resume_ext:
        raise ValidationError(
            f"Resume must be one of: {', '.join(settings.allowed_resume_ext)}."
        )
    if not content_type or content_type not in settings.allowed_resume_mime:
        # Some browsers send application/octet-stream even for valid PDFs; check extension.
        if suffix and suffix in settings.allowed_resume_ext:
            return
        raise ValidationError("Unexpected file type.")


def set_primary(db: Session, *, student: Student, resume_id: str) -> Resume:
    resume = db.get(Resume, resume_id)
    if resume is None or resume.student_id != student.id:
        raise NotFoundError("Resume not found.")
    db.query(Resume).filter(Resume.student_id == student.id).update({"is_primary": False})
    resume.is_primary = True
    db.commit()
    db.refresh(resume)
    return resume


def delete_resume(db: Session, *, student: Student, resume_id: str) -> None:
    resume = db.get(Resume, resume_id)
    if resume is None or resume.student_id != student.id:
        raise NotFoundError("Resume not found.")
    if resume.is_primary:
        db.query(Resume).filter(
            Resume.student_id == student.id, Resume.id != resume.id
        ).update({"is_primary": True}, synchronize_session=False)
    try:
        path = Path(resume.storage_path)
        if path.exists():
            path.unlink()
    except OSError:
        pass  # a dangling row is worse than a missing file
    db.delete(resume)
    db.commit()


def _detect_skills(text: str) -> list[str]:
    """Deterministic skill keywords from text. AI-provided lists ride the
    analysis path, not this; this guard keeps the Resume row usable offline."""
    candidates = [
        "python", "java", "c++", "cpp", "javascript", "typescript", "react",
        "node.js", "nodejs", "express", "sql", "mysql", "postgresql", "mongodb",
        "html", "css", "git", "docker", "kubernetes", "aws", "azure", "gcp",
        "machine learning", "deep learning", "data structures", "algorithms",
        "dbms", "computer networks", "oops", "operating systems", "django",
        "flask", "fastapi", "pandas", "numpy", "tensorflow", "pytorch", "tailwind",
    ]
    lowered = text.lower()
    return sorted({s for s in candidates if s in lowered})


# --------------------------------------------------------------------------- #
# AI-assisted analysis (never authoritative for eligibility)
# --------------------------------------------------------------------------- #
def analyze_resume_against_drive(
    db: Session,
    *,
    student: Student,
    drive_id: str,
    resume_id: str | None = None,
    actor_ctx: AuditContext | None = None,
) -> dict:
    """Return a ResumeAnalysisResult-shaped dict, always computed server-side."""
    drive = db.get(PlacementDrive, drive_id)
    if drive is None or drive.institution_id != student.institution_id:
        raise NotFoundError("Drive not found.")

    resume = None
    if resume_id:
        resume = db.get(Resume, resume_id)
        if resume is None or resume.student_id != student.id:
            raise NotFoundError("Resume not found.")
    if resume is None:
        resume = (
            db.query(Resume)
            .filter(Resume.student_id == student.id, Resume.is_primary.is_(True))
            .first()
        )
    if resume is None:
        raise ValidationError("Upload a resume before running the analysis.")

    resume_skills = set(resume.parsed_skills)
    drive_skill_names = [row.skill.name for row in db.query(DriveSkill).filter(DriveSkill.drive_id == drive_id).all()]
    required = drive_skill_names or _skills_from_jd(drive.jd_text)

    matched, partial, missing = match_skills(resume_skills, required)
    skill_match = round(len(matched) / len(required), 4) if required else 1.0

    # AI advisory pass (optional): refine the missing/matched labels and write
    # coaching text. Failures fall back to the deterministic result.
    ai_ok = True
    ai_note = ""
    try:
        verdict = ai_service.compare_skills(list(resume_skills), required)
        if verdict.value:
            _persist_analysis(
                db,
                institution_id=student.institution_id,
                analysis_type="resume_jd_match",
                student=student,
                drive_id=drive_id,
                resume=resume,
                provider=verdict.provider,
                model=verdict.model,
                schema_name="SkillComparisonSchema",
                result=verdict.value.model_dump(),
                raw_response=verdict.raw_response,
                latency_ms=verdict.latency_ms,
            )
    except ai_service.AIError:
        ai_ok = False
        ai_note = "AI provider unavailable; result computed deterministically."

    analysis = {
        "skill_match": skill_match,
        "matched_skills": sorted(matched),
        "partial_skills": sorted(partial),
        "missing_skills": sorted(missing),
        "resume_skills_detected": sorted(resume_skills),
        "drive_required_skills": sorted(required),
        "skill_gap_analysis": [
            {"skill": s, "status": "matched", "recommendation": "Keep it current in your CV."}
            for s in sorted(matched)
        ]
        + [
            {"skill": s, "status": "partial", "recommendation": "Add specific tools/projects to strengthen it."}
            for s in sorted(partial)
        ]
        + [
            {"skill": s, "status": "missing", "recommendation": "Pick one project that demonstrates this skill."}
            for s in sorted(missing)
        ],
        "feedback_text": ai_note or _feedback_text(skill_match, len(required)),
        "summary": (
            f"{len(matched)} of {len(required)} required skills matched "
            f"({len(partial)} partial) for {drive.title}."
        ),
        "analyzed_at": datetime.now().isoformat(),
    }
    if not ai_ok and not analysis["feedback_text"]:
        analysis["feedback_text"] = "AI provider unavailable; result computed deterministically."
    record(
        db,
        action="analysis.resume_jd_run",
        context=actor_ctx,
        entity_type="analysis",
        entity_id=resume.id,
        detail={"drive_id": drive_id, "skill_match": skill_match},
    )
    db.commit()
    return analysis


def build_prep_roadmap(
    db: Session,
    *,
    student: Student,
    drive_id: str,
    actor_ctx: AuditContext | None = None,
) -> dict:
    drive = db.get(PlacementDrive, drive_id)
    if drive is None or drive.institution_id != student.institution_id:
        raise NotFoundError("Drive not found.")
    resume = (
        db.query(Resume)
        .filter(Resume.student_id == student.id, Resume.is_primary.is_(True))
        .first()
    )
    resume_skills = set(resume.parsed_skills) if resume else set()

    drive_skill_names = [row.skill.name for row in db.query(DriveSkill).filter(DriveSkill.drive_id == drive_id).all()]
    required = drive_skill_names or _skills_from_jd(drive.jd_text)
    _, _, missing = match_skills(resume_skills, required)

    try:
        ai_result = ai_service.build_roadmap(list(missing), list(resume_skills), drive.title)
        roadmap = {
            "drive_id": drive_id,
            "priority_skills": ai_result.value.priority_skills or sorted(missing),
            "roadmap_steps": _roadmap_steps_from_ai(ai_result.value),
            "suggested_practice": ai_result.value.suggested_resources or _practice_hints(sorted(missing)),
            "skill_gaps": [
                {"skill": s, "status": "missing", "recommendation": _practice_hints([s])[0]}
                for s in sorted(missing)
            ],
            "disclaimer": "AI-generated guidance based on publicly available recruitment "
            "information; placement cell criteria always take precedence.",
        }
        _persist_analysis(
            db,
            institution_id=student.institution_id,
            analysis_type="prep_roadmap",
            student=student,
            drive_id=drive_id,
            resume=resume,
            provider=ai_result.provider,
            model=ai_result.model,
            schema_name="PreparationRoadmapSchema",
            result=ai_result.value.model_dump(),
            latency_ms=ai_result.latency_ms,
        )
    except ai_service.AIError:
        roadmap = {
            "drive_id": drive_id,
            "priority_skills": sorted(missing),
            "roadmap_steps": _roadmap_steps(sorted(missing)),
            "suggested_practice": _practice_hints(sorted(missing)),
            "skill_gaps": [
                {"skill": s, "status": "missing", "recommendation": _practice_hints([s])[0]}
                for s in sorted(missing)
            ],
            "disclaimer": "Deterministic fallback (AI unavailable).",
        }
    record(
        db,
        action="analysis.roadmap_run",
        context=actor_ctx,
        entity_type="analysis",
        entity_id=drive_id,
        detail={"drive_id": drive_id, "missing_count": len(missing)},
    )
    db.commit()
    return roadmap


def _persist_analysis(
    db: Session,
    *,
    institution_id: str,
    analysis_type: str,
    student: Student | None,
    drive_id: str | None,
    resume: Resume | None,
    provider: str,
    model: str,
    schema_name: str,
    result: dict,
    raw_response: str | None = None,
    latency_ms: int | None = None,
) -> None:
    row = AIAnalysis(
        institution_id=institution_id,
        analysis_type=analysis_type,
        student_id=student.id if student else None,
        drive_id=drive_id,
        resume_id=resume.id if resume else None,
        provider=provider,
        model=model,
        schema_name=schema_name,
        result=result,
        raw_response=raw_response,
        status="succeeded",
        latency_ms=latency_ms,
    )
    db.add(row)
    db.flush()


def _skills_from_jd(jd_text: str | None) -> list[str]:
    return _detect_skills(jd_text or "")


def _feedback_text(skill_match: float, total_required: int) -> str:
    if total_required == 0:
        return "This drive lists no required skills. Ensure your resume is polished."
    if skill_match >= 0.75:
        return "Strong match. Focus on sharpening the missing items before the drive."
    if skill_match >= 0.4:
        return "Moderate match. Prioritise closing the missing skill gaps listed below."
    return "Your profile currently covers few of the required skills. Consider targeted prep before applying."


def _roadmap_steps(missing: list[str]) -> list[str]:
    if not missing:
        return ["No critical gaps. Rehearse mock interviews and keep your resume current."]
    return [
        f"Week 1-2: Build a small portfolio project using {', '.join(missing[:3])}.",
        "Week 3: Solve standard problems covering the missing topics on a daily track.",
        "Week 4: Update your resume with the new projects and self-review against the JD.",
    ]


def _roadmap_steps_from_ai(ai: ai_service.PreparationRoadmapSchema) -> list[str]:
    if ai.timeline_weeks:
        return [
            f"Week {week['week']}: {', '.join(week.get('skills', []))}" for week in ai.timeline_weeks
        ]
    return _roadmap_steps(ai.priority_skills)


def _practice_hints(missing: list[str]) -> list[str]:
    if not missing:
        return ["Maintain a solution bank of the problems you have solved."]
    return [
        f"Topic track: {skill}" for skill in missing[:5]
    ]