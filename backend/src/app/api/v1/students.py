"""Student-facing profile, skills, and read-only institutional data."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.deps import (
    CurrentUser,
    get_actor_context,
    get_current_user,
    get_student_record,
    require_student,
)
from app.core.config import settings
from app.core.ratelimit import route_limit
from app.db.models import Student
from app.db.session import get_db
from app.schemas.students import (
    SkillRead,
    SkillUpsert,
    StudentDashboard,
    StudentDetail,
    StudentSelfUpdate,
)
from app.services import notifications as notif_service
from app.services import students as student_service

router = APIRouter(prefix="/students", tags=["students"])


@router.get("/me", response_model=StudentDetail)
def my_profile(
    _current: CurrentUser = Depends(get_current_user),
    student: Student = Depends(get_student_record),
) -> StudentDetail:
    return _student_to_detail(student)


@router.get("/me/dashboard", response_model=StudentDashboard)
def my_dashboard(
    _current: CurrentUser = Depends(require_student),
    student: Student = Depends(get_student_record),
    db: Session = Depends(get_db),
) -> StudentDashboard:
    notif_service.ensure_deadline_reminders(db, user=student.user, student=student)
    return StudentDashboard(**student_service.build_dashboard(db, user=student.user, student=student))


@router.patch("/me", response_model=StudentDetail)
@route_limit(settings.rate_limit_write)
def update_my_profile(
    body: StudentSelfUpdate,
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    student: Student = Depends(get_student_record),
    db: Session = Depends(get_db),
) -> StudentDetail:
    actor = get_actor_context(request, current)
    student_service.update_self_profile(
        db,
        student=student,
        values=body.model_dump(exclude_unset=True),
        actor_ctx=actor,
    )
    return _student_to_detail(student)


@router.get("/me/skills", response_model=list[SkillRead])
def my_skills(
    _current: CurrentUser = Depends(get_current_user),
    student: Student = Depends(get_student_record),
) -> list[SkillRead]:
    return [
        SkillRead(
            id=row.skill.id,
            name=row.skill.name,
            normalized_name=row.skill.normalized_name,
            category=row.skill.category,
            proficiency=row.proficiency,
            years_experience=row.years_experience,
            source=row.source,
            is_verified=row.is_verified,
        )
        for row in _sorted_skills(student.skills)
    ]


@router.put("/me/skills", response_model=list[SkillRead])
@route_limit(settings.rate_limit_write)
def replace_my_skills(
    body: list[SkillUpsert],
    request: Request,
    current: CurrentUser = Depends(get_current_user),
    student: Student = Depends(get_student_record),
    db: Session = Depends(get_db),
) -> list[SkillRead]:
    actor = get_actor_context(request, current)
    student_service.replace_skills(
        db,
        student=student,
        skills=[b.model_dump(exclude_unset=True) for b in body],
        actor_ctx=actor,
    )
    return [
        SkillRead(
            id=row.skill.id,
            name=row.skill.name,
            normalized_name=row.skill.normalized_name,
            category=row.skill.category,
            proficiency=row.proficiency,
            years_experience=row.years_experience,
            source=row.source,
            is_verified=row.is_verified,
        )
        for row in _sorted_skills(student.skills)
    ]


def _sorted_skills(rows: list) -> list:
    return sorted(rows, key=lambda r: r.skill.name.lower())


def _student_to_detail(student: Student) -> StudentDetail:
    dept = student.department
    user = student.user
    return StudentDetail(
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
        profile_headline=student.profile_headline,
        about=student.about,
        phone=student.phone,
        location=student.location,
        portfolio_url=student.portfolio_url,
        linkedin_url=student.linkedin_url,
        github_url=student.github_url,
        gender=student.gender,
        date_of_birth=student.date_of_birth,
    )