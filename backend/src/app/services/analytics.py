"""Analytics service: funnel, department stats, status distribution, top drives.

All counts are institution-scoped. Queries are deliberately straightforward so
the numbers are auditable against the raw tables.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import (
    APP_OFFERED,
    APP_SHORTLISTED,
    Application,
    Company,
    Department,
    PlacementDrive,
    Student,
)


def summary(db: Session, *, institution_id: str) -> dict:
    total_students = db.query(func.count(Student.id)).filter(
        Student.institution_id == institution_id, Student.is_active.is_(True)
    ).scalar() or 0

    total_drives = db.query(func.count(PlacementDrive.id)).filter(
        PlacementDrive.institution_id == institution_id
    ).scalar() or 0
    published_drives = db.query(func.count(PlacementDrive.id)).filter(
        PlacementDrive.institution_id == institution_id,
        PlacementDrive.status == "published",
    ).scalar() or 0

    total_applications = db.query(func.count(Application.id)).filter(
        Application.institution_id == institution_id
    ).scalar() or 0
    unique_applicants = (
        db.query(func.count(func.distinct(Application.student_id)))
        .filter(Application.institution_id == institution_id)
        .scalar()
        or 0
    )
    apps_per_drive = round(total_applications / published_drives, 2) if published_drives else 0.0

    funnel = _overall_funnel(db, institution_id)
    department_stats = _department_stats(db, institution_id)
    status_stats = _status_stats(db, institution_id)
    top_drives = _top_drives(db, institution_id)

    return {
        "total_students": total_students,
        "total_drives": total_drives,
        "published_drives": published_drives,
        "total_applications": total_applications,
        "unique_applicants": unique_applicants,
        "applications_per_drive": apps_per_drive,
        "overall_funnel": funnel,
        "department_stats": department_stats,
        "status_stats": status_stats,
        "top_drives": top_drives,
    }


def _overall_funnel(db: Session, institution_id: str) -> list[dict]:
    rows = (
        db.query(Application.status, func.count(Application.id))
        .filter(Application.institution_id == institution_id)
        .group_by(Application.status)
        .all()
    )
    counts = dict(rows)
    order = [
        ("applied", "Applied"),
        ("in_review", "In review"),
        ("shortlisted", "Shortlisted"),
        ("interview", "Interview"),
        ("offered", "Offered"),
        ("offer_accepted", "Offer accepted"),
        ("rejected", "Rejected"),
        ("withdrawn", "Withdrawn"),
    ]
    return [{"label": label, "count": counts.get(key, 0)} for key, label in order]


def _department_stats(db: Session, institution_id: str) -> list[dict]:
    sub = select(Student.department_id, func.count(Student.id)).where(
        Student.institution_id == institution_id, Student.is_active.is_(True)
    ).group_by(Student.department_id).subquery()

    joined = (
        db.query(
            Department.code.label("department_code"),
            Department.name.label("department_name"),
            func.coalesce(sub.c.count, 0).label("students"),
            func.count(Application.id).label("applications"),
            func.sum(case_offered(Application.status)).label("placed"),
        )
        .select_from(Department)
        .outerjoin(sub, Department.id == sub.c.department_id)
        .outerjoin(
            Application,
            (Application.student_id.in_(select(Student.id).where(Student.department_id == Department.id)))
            & (Application.institution_id == institution_id),
        )
        .filter(Department.institution_id == institution_id)
        .group_by(Department.id, sub.c.count)
        .order_by(Department.code)
        .all()
    )
    return [
        {
            "department_code": r.department_code,
            "department_name": r.department_name,
            "students": r.students,
            "applications": r.applications,
            "placed": r.placed or 0,
        }
        for r in joined
    ]


def case_offered(status):
    from sqlalchemy import case

    return case((status.in_([APP_OFFERED, "offer_accepted"]), 1), else_=0)


def _status_stats(db: Session, institution_id: str) -> list[dict]:
    rows = (
        db.query(Application.status, func.count(Application.id))
        .filter(Application.institution_id == institution_id)
        .group_by(Application.status)
        .order_by(func.count(Application.id).desc())
        .all()
    )
    return [{"status": key, "count": count} for key, count in rows]


def _top_drives(db: Session, institution_id: str) -> list[dict]:
    rows = (
        db.query(
            PlacementDrive.id.label("drive_id"),
            PlacementDrive.title.label("drive_title"),
            Company.name.label("company_name"),
            func.count(Application.id).label("apps_total"),
            func.sum(case_offered(Application.status)).label("apps_offered"),
            func.sum(case_shortlisted(Application.status)).label("apps_shortlisted"),
        )
        .select_from(PlacementDrive)
        .outerjoin(Company, Company.id == PlacementDrive.company_id)
        .outerjoin(Application, Application.drive_id == PlacementDrive.id)
        .filter(PlacementDrive.institution_id == institution_id)
        .group_by(PlacementDrive.id, Company.name)
        .order_by(func.count(Application.id).desc())
        .limit(10)
        .all()
    )
    return [
        {
            "drive_id": r.drive_id,
            "drive_title": r.drive_title,
            "company_name": r.company_name or "",
            "apps_total": r.apps_total,
            "apps_shortlisted": r.apps_shortlisted or 0,
            "apps_offered": r.apps_offered or 0,
        }
        for r in rows
    ]


def case_shortlisted(status):
    from sqlalchemy import case

    return case((status == APP_SHORTLISTED, 1), else_=0)