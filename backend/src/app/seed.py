"""Synthetic-data seeder for local development and demos.

Creates the institution, departments, an admin account, companies, students
(with login passwords), resumes, drives (draft / published / JD-pending), and a
bounded set of applications so every screen of the UI has data.

The seeder exercises the SAME services the API uses (provision_student,
drive_service.create_drive / publish_drive, ApplicationService.create,
resume_service.upload_resume), so seeded rows are structurally identical to
rows the product produces. It is idempotent: re-running never duplicates a
row, it only tops up data that is missing.

Usage (from the backend directory, with the venv active):

    python -m app.seed                      # sensible demo defaults
    python -m app.seed --students 40        # more students
    python -m app.seed --no-applications    # skip applications/resumes

Credentials: the demo admin and student passwords come from the
SEED_ADMIN_PASSWORD / SEED_STUDENT_PASSWORD environment variables; when unset,
random passwords are generated and printed once at seed time.

Production safety: this module refuses to run when environment == "production".
"""

from __future__ import annotations

import argparse
import secrets
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import PermissionError_, ValidationError
from app.core.security import hash_password
from app.db.models import (
    Application,
    Company,
    Department,
    PlacementDrive,
    Student,
    User,
)
from app.db.session import SessionLocal
from app.services import drives as drive_service
from app.services import students as student_service
from app.services.applications import ApplicationService
from app.services.resumes import upload_resume
from app.services.users import get_user_by_email, init_institution

ADMIN_EMAIL = settings.seed_admin_email or "admin@kletech.example.edu"


def seed_credentials() -> tuple[str, str]:
    """Resolve demo credentials from settings; generate random ones when the
    operator did not provide them. Returns (admin_password, student_password).

    Generated passwords are shown once at seed time (printed by ``main()``).
    Never generates for production — ``seed()`` refuses to run there."""

    admin_password = settings.seed_admin_password or secrets.token_urlsafe(12)
    student_password = settings.seed_student_password or secrets.token_urlsafe(12)
    return admin_password, student_password


DEPARTMENTS: list[tuple[str, str, str, bool]] = [
    ("CSE", "Computer Science & Engineering", "B.E.", True),
    ("ISE", "Information Science & Engineering", "B.E.", True),
    ("ECE", "Electronics & Communication", "B.E.", True),
    ("AIML", "AI & Machine Learning", "B.E.", True),
    ("ME", "Mechanical Engineering", "B.E.", False),
]

COMPANIES: list[dict] = [
    {
        "name": "Nimbus Technologies",
        "website": "https://nimbus.example.com",
        "industry": "Software & Cloud Services",
        "location": "Bengaluru, India",
        "about": "Cloud infrastructure and platform engineering at scale.",
        "contact_email": "careers@nimbus.example.com",
        "tiers": ["Dream"],
        "reputation_score": 4.6,
    },
    {
        "name": "DataWeave Analytics",
        "website": "https://dataweave.example.com",
        "industry": "Data Analytics",
        "location": "Hyderabad, India",
        "about": "Data science and business intelligence for consumer businesses.",
        "contact_email": "talent@dataweave.example.com",
        "tiers": ["Dream"],
        "reputation_score": 4.2,
    },
    {
        "name": "VoltMotive",
        "website": "https://voltmotive.example.com",
        "industry": "Embedded Systems",
        "location": "Pune, India",
        "about": "Automotive electronics and embedded firmware.",
        "contact_email": "hr@voltmotive.example.com",
        "tiers": ["Core"],
        "reputation_score": 4.0,
    },
    {
        "name": "Pixelforge Studios",
        "website": "https://pixelforge.example.com",
        "industry": "Product / UI Engineering",
        "location": "Bengaluru, India",
        "about": "Design-led web and mobile product company.",
        "contact_email": "jobs@pixelforge.example.com",
        "tiers": ["Mass Recruiter"],
        "reputation_score": 3.7,
    },
    {
        "name": "SecureGrid Systems",
        "website": "https://securegrid.example.com",
        "industry": "Cybersecurity",
        "location": "Mumbai, India",
        "about": "Application security, pen-testing and campus hiring for fresh graduates.",
        "contact_email": "careers@securegrid.example.com",
        "tiers": ["Mass Recruiter"],
        "reputation_score": 3.9,
    },
    {
        "name": "BluePeak Logistics",
        "website": "https://bluepeak.example.com",
        "industry": "Logistics & IoT",
        "location": "Chennai, India",
        "about": "IoT-enabled supply chain logistics, nationwide campus drives.",
        "contact_email": "talent@bluepeak.example.com",
        "tiers": ["Core"],
        "reputation_score": 3.5,
    },
]

STUDENTS: list[dict] = [
    {"name": "Aarav Sharma", "dept": "CSE", "batch": 2026, "cgpa": 8.7},
    {"name": "Sneha Patil", "dept": "CSE", "batch": 2026, "cgpa": 9.1},
    {"name": "Rohan Deshmukh", "dept": "ISE", "batch": 2026, "cgpa": 7.4},
    {"name": "Priya Nair", "dept": "ECE", "batch": 2026, "cgpa": 6.8},
    {"name": "Arjun Reddy", "dept": "CSE", "batch": 2025, "cgpa": 8.2},
    {"name": "Ananya Iyer", "dept": "AIML", "batch": 2026, "cgpa": 9.4},
    {"name": "Vikram Singh", "dept": "ME", "batch": 2025, "cgpa": 7.1},
    {"name": "Meera Menon", "dept": "ECE", "batch": 2027, "cgpa": 7.9},
    {"name": "Karthik Rao", "dept": "ISE", "batch": 2025, "cgpa": 8.0},
    {"name": "Divya Kulkarni", "dept": "AIML", "batch": 2027, "cgpa": 8.8},
    {"name": "Aditya Joshi", "dept": "CSE", "batch": 2027, "cgpa": 6.5, "backlogs": 1},
    {"name": "Pooja Rane", "dept": "ISE", "batch": 2026, "cgpa": 9.0},
    {"name": "Naveen Kumar", "dept": "ME", "batch": 2025, "cgpa": 6.2},
    {"name": "Ishita Bhattacharya", "dept": "ECE", "batch": 2027, "cgpa": None},
    {"name": "Siddharth Gowda", "dept": "CSE", "batch": 2026, "cgpa": 7.7},
    {"name": "Tanvi Shetty", "dept": "AIML", "batch": 2025, "cgpa": 8.5},
    {"name": "Rahul Verma", "dept": "ISE", "batch": 2027, "cgpa": 7.0},
    {"name": "Ankita Mishra", "dept": "ECE", "batch": 2026, "cgpa": 7.3, "backlogs": 1},
    {"name": "Varun Pillai", "dept": "CSE", "batch": 2025, "cgpa": 6.9},
    {"name": "Neha Agarwal", "dept": "AIML", "batch": 2026, "cgpa": 8.9},
    {"name": "Manoj Hegde", "dept": "ISE", "batch": 2026, "cgpa": 7.6},
    {"name": "Ritika Shah", "dept": "ME", "batch": 2027, "cgpa": 6.6},
    {"name": "Deepak Naik", "dept": "ECE", "batch": 2025, "cgpa": 7.2},
    {"name": "Shreya Das", "dept": "CSE", "batch": 2027, "cgpa": 8.3},
]

RESUME_SKILLS: dict[str, list[str]] = {
    "python": ["python", "fastapi", "pandas", "numpy", "git", "sql"],
    "backend": ["python", "node.js", "express", "sql", "postgresql", "docker", "git"],
    "frontend": ["javascript", "typescript", "react", "html", "css", "git"],
    "ml": ["python", "machine learning", "tensorflow", "pandas", "numpy"],
    "embedded": ["c++", "git", "algorithms", "operating systems"],
}

DRIVES: list[dict] = [
    {
        "company": "Nimbus Technologies",
        "title": "Software Engineer Trainee",
        "role_title": "SWE Trainee",
        "employment_type": "full_time",
        "location": "Bengaluru",
        "ctc_lpa": "12-16 LPA",
        "description": "Campus hiring for cloud product engineering. Strong DSA and backend fundamentals expected.",
        "status": "draft",
        "criteria": [
            {"criterion_type": "cgpa_min", "parameters": {"value": 7.0}},
            {"criterion_type": "backlog_max", "parameters": {"active_backlogs": 0}},
            {"criterion_type": "departments", "parameters": {"departments": ["CSE", "ISE", "AIML"]}},
            {"criterion_type": "batch_years", "parameters": {"years": [2025, 2026]}},
        ],
        "required_skills": ["python", "sql", "data structures", "git"],
    },
    {
        "company": "DataWeave Analytics",
        "title": "Data Analyst Intern",
        "role_title": "Data Analyst Intern",
        "employment_type": "internship",
        "location": "Hyderabad",
        "stipend": "₹25,000/month",
        "description": "Six-month internship building dashboards and statistical models with business teams.",
        "status": "published",
        "criteria": [
            {"criterion_type": "cgpa_min", "parameters": {"value": 6.5}},
            {"criterion_type": "backlog_max", "parameters": {"active_backlogs": 0}},
            {"criterion_type": "departments", "parameters": {"departments": ["CSE", "ISE", "ECE", "AIML"]}},
            {"criterion_type": "batch_years", "parameters": {"years": [2026, 2027]}},
        ],
        "required_skills": ["python", "sql", "pandas", "statistics"],
        "rounds": [
            {
                "position": 1,
                "round_type": "online_assessment",
                "title": "Online Assessment",
                "topics": ["python", "sql", "aptitude"],
            },
            {
                "position": 2,
                "round_type": "technical_interview",
                "title": "Technical Interview",
                "topics": ["pandas", "statistics", "sql"],
            },
            {
                "position": 3,
                "round_type": "hr_interview",
                "title": "HR Interview",
                "topics": ["communication", "teamwork"],
            },
        ],
    },
    {
        "company": "VoltMotive",
        "title": "Embedded Systems Engineer",
        "role_title": "Embedded Engineer",
        "employment_type": "full_time",
        "location": "Pune",
        "ctc_lpa": "9-12 LPA",
        "description": "Automotive embedded firmware development with C/C++ and RTOS experience.",
        "status": "published",
        "criteria": [
            {"criterion_type": "cgpa_min", "parameters": {"value": 7.5}},
            {"criterion_type": "backlog_max", "parameters": {"active_backlogs": 0}},
            {"criterion_type": "departments", "parameters": {"departments": ["ECE"]}},
            {"criterion_type": "batch_years", "parameters": {"years": [2026]}},
        ],
        "required_skills": ["c++", "embedded systems", "git"],
        "rounds": [
            {
                "position": 1,
                "round_type": "online_assessment",
                "title": "Online Assessment",
                "topics": ["c++", "aptitude", "embedded systems"],
            },
            {
                "position": 2,
                "round_type": "technical_interview",
                "title": "Technical Interview",
                "topics": ["embedded systems", "c++", "operating systems"],
            },
            {
                "position": 3,
                "round_type": "hr_interview",
                "title": "HR Interview",
                "topics": ["communication"],
            },
        ],
    },
    {
        "company": "Pixelforge Studios",
        "title": "Frontend Engineer",
        "role_title": "Frontend Engineer",
        "employment_type": "full_time",
        "location": "Bengaluru",
        "ctc_lpa": "10-14 LPA",
        "description": "Product engineering for web apps. React/TypeScript discipline required.",
        "status": "draft",
        "criteria": [
            {"criterion_type": "cgpa_min", "parameters": {"value": 6.0}},
            {"criterion_type": "backlog_max", "parameters": {"active_backlogs": 2}},
            {"criterion_type": "departments", "parameters": {"departments": ["CSE", "ISE", "ECE", "AIML"]}},
            {"criterion_type": "batch_years", "parameters": {"years": [2025, 2026, 2027]}},
        ],
        "required_skills": ["javascript", "typescript", "react", "html", "css"],
    },
    {
        "company": "SecureGrid Systems",
        "title": "Security Operations Analyst",
        "role_title": "SOC Analyst",
        "employment_type": "full_time",
        "location": "Mumbai",
        "ctc_lpa": "6-9 LPA",
        "description": "Entry-level security operations role; JD uploaded pending extraction confirmation.",
        "status": "draft",
        "jd_pending": True,
        "jd_text": (
            "We are hiring Security Operations Analysts for our Bengaluru SOC. "
            "Strong fundamentals in computer networks, operating systems, and python are required. "
            "Familiarity with linux, bash, and SIEM tools is a plus."
        ),
        "criteria": [],
        "required_skills": [],
    },
]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--students", type=int, default=24, help="Number of student profiles to seed")
    parser.add_argument(
        "--no-applications", action="store_true", help="Do not seed applications or resumes"
    )
    args = parser.parse_args()

    if settings.environment == "production":
        raise SystemExit("Refusing to seed the database in production.")

    db = SessionLocal()
    try:
        summary = seed(db, student_count=args.students, with_applications=not args.no_applications)
        db.commit()
        print("Seeded successfully:")
        for key, value in summary.items():
            print(f"  {key}: {value}")
        if summary.get("admin_password"):
            print("\nDemo credentials (set the SEED_*_PASSWORD variables to pin these):")
            print(f"  admin ({summary['admin']}): {summary['admin_password']}")
            if summary.get("student_password"):
                print(f"  students: {summary['student_password']}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def seed(db: Session, *, student_count: int = 24, with_applications: bool = True) -> dict:
    """Seed the database. Idempotent; safe to call from startup or a script."""
    init_institution(db)
    inst_id = settings.institution.code

    admin_password, student_password = seed_credentials()
    admin, admin_created = _ensure_admin(db, inst_id, admin_password)
    _ensure_departments(db, inst_id)

    existing_companies = {
        name
        for (name,) in db.query(Company.name).filter(Company.institution_id == inst_id).all()
    }
    created_companies = 0
    companies = []
    for spec in COMPANIES:
        company = _ensure_company(db, inst_id, spec)
        if spec["name"] not in existing_companies:
            created_companies += 1
        companies.append(company)

    created_students = 0
    created_resumes = 0
    for spec in STUDENTS[:student_count]:
        if _ensure_student(db, inst_id, spec, student_password):
            created_students += 1
            if with_applications and spec["dept"] in {"CSE", "ISE", "AIML"}:
                created_resumes += _ensure_resume_for(db, spec)

    created_drives = 0
    created_draft = 0
    created_published = 0
    for idx, spec in enumerate(DRIVES):
        company = companies[idx % len(companies)]
        new_drive = _drive_exists(db, inst_id, company.id, spec["title"]) is None
        drive = _ensure_drive(db, inst_id, company.id, spec, admin.id)
        if new_drive:
            created_drives += 1
            if drive.status == "draft":
                created_draft += 1
            else:
                created_published += 1

    applications = 0
    if with_applications:
        published = (
            db.query(PlacementDrive)
            .filter(
                PlacementDrive.institution_id == inst_id,
                PlacementDrive.status == "published",
            )
            .all()
        )
        students = db.query(Student).filter(Student.institution_id == inst_id).all()
        for drive in published:
            for student in students:
                if db.query(Application).filter_by(
                    student_id=student.id, drive_id=drive.id
                ).first():
                    continue
                if applications >= 16:
                    break
                try:
                    ApplicationService(db).create(student=student, drive_id=drive.id)
                    applications += 1
                except PermissionError_:
                    continue  # student not eligible; keep the pool realistic
            if applications >= 16:
                break

    # Set a couple of applications to a later stage so the admin funnel is non-trivial.
    _advance_application_statuses(db, inst_id)

    return {
        "institution": settings.institution.code,
        "admin": admin.email,
        "admin_password": admin_password if (admin_created or settings.seed_admin_password) else None,
        "student_password": student_password if (created_students or settings.seed_student_password) else None,
        "students": created_students,
        "resumes": created_resumes,
        "companies": created_companies,
        "drives_created": created_drives,
        "drives_draft": created_draft,
        "drives_published": created_published,
        "applications": applications,
    }


def _ensure_admin(db: Session, inst_id: str, admin_password: str) -> tuple[User, bool]:
    """Return (admin, created_now).

    An operator-provided password is enforced on every run so SEED_ADMIN_PASSWORD
    stays convergent; a generated password is only written on first creation.
    """
    existing = get_user_by_email(db, ADMIN_EMAIL, inst_id)
    if existing:
        if settings.seed_admin_password and existing.password_hash != hash_password(
            settings.seed_admin_password
        ):
            existing.password_hash = hash_password(settings.seed_admin_password)
        return existing, False
    user = User(
        institution_id=inst_id,
        email=ADMIN_EMAIL,
        password_hash=hash_password(admin_password),
        role="placement_admin",
        full_name="Placement Cell Admin",
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user, True


def _ensure_departments(db: Session, inst_id: str) -> None:
    for code, name, degree, technical in DEPARTMENTS:
        if db.query(Department).filter_by(institution_id=inst_id, code=code).first():
            continue
        db.add(
            Department(
                institution_id=inst_id,
                code=code,
                name=name,
                degree=degree,
                is_technical=technical,
            )
        )
        db.flush()


def _ensure_company(db: Session, inst_id: str, spec: dict) -> Company:
    existing = (
        db.query(Company)
        .filter(Company.institution_id == inst_id, Company.name == spec["name"])
        .first()
    )
    if existing:
        return existing
    company = Company(institution_id=inst_id, **spec)
    db.add(company)
    db.flush()
    return company


def _edu_email(spec: dict) -> str:
    first, last = spec["name"].lower().split(" ", 1)
    return f"{first}.{last.replace(' ', '').replace('-', '')}@student.kletech.example.edu"


def _ensure_student(db: Session, inst_id: str, spec: dict, student_password: str) -> bool:
    email = _edu_email(spec)
    if get_user_by_email(db, email, inst_id):
        return False
    backlogs = spec.get("backlogs", 0)
    seq = _college_seq(db, inst_id)
    college_id = f"1KS{spec['batch'] % 100}{spec['dept']}{seq}"
    # batch 2025 -> born 2004; batch 2027 -> born 2002 (22-24 in 2026).
    birth = datetime(2029 - spec["batch"], 6, 15, tzinfo=UTC).date()
    _, student, _ = student_service.provision_student(
        db,
        institution_id=inst_id,
        college_id=college_id,
        email=email,
        full_name=spec["name"],
        department_code=spec["dept"],
        batch_year=spec["batch"],
        cgpa=spec["cgpa"],
        backlog_count=backlogs,
        active_backlogs=backlogs,
        gender="female" if spec["name"].split(" ", 1)[0] in {
            "Sneha", "Priya", "Ananya", "Meera", "Divya", "Pooja",
            "Ishita", "Tanvi", "Ankita", "Neha", "Ritika", "Shreya",
        } else "male",
        date_of_birth=birth,
        phone=f"+91{9000000000 + seq}",
        academic_data_verified=True,
        temporary_password=student_password,
        send_activation=False,
    )
    db.flush()
    _attach_seed_skills(db, student, spec)
    return True


def _college_seq(db: Session, inst_id: str) -> int:
    return db.query(Student).filter(Student.institution_id == inst_id).count() + 1


def _attach_seed_skills(db: Session, student: Student, spec: dict) -> None:
    dept = spec["dept"]
    skills: list[dict] = []
    if dept == "CSE":
        base = ["python", "sql", "data structures"]
    elif dept == "ISE":
        base = ["python", "sql", "javascript"]
    elif dept == "ECE":
        base = ["c++", "operating systems", "embedded basics"]
    else:
        base = ["python", "statistics", "machine learning"]
    for name in base:
        skills.append({"name": name, "proficiency": 4 if spec["cgpa"] and spec["cgpa"] >= 7.5 else 3})
    student_service.replace_skills(db, student=student, skills=skills)


def _ensure_resume_for(db: Session, spec: dict) -> int:
    student = db.query(Student).join(User).filter(
        Student.institution_id == settings.institution.code,
        User.email == _edu_email(spec),
    ).first()
    if student is None or student.resumes:
        return 0
    category = {"CSE": "backend", "ISE": "frontend", "AIML": "ml"}.get(spec["dept"], "backend")
    skills = RESUME_SKILLS[category]
    text = (
        f"{spec['name']} - {spec['dept']} batch of {spec['batch']}\n"
        "Focused on building reliable, well-tested software.\n"
        f"Skills: {', '.join(skills)}\n"
        "Projects: campus placement portal, IoT dashboard, ML experiment tracker."
    )
    upload_resume(
        db,
        student=student,
        filename=f"{category}-resume-{spec['batch']}.pdf",
        content_type="application/pdf",
        data=_text_to_pdf(text),
    )
    return 1


def _text_to_pdf(text: str) -> bytes:
    """Render a minimal single-page PDF. PyMuPDF is a declared dependency, so we
    feed the real extraction pipeline rather than faking a Resume row."""
    import pymupdf

    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), text, fontsize=11)
    return document.tobytes()


def _drive_exists(db: Session, inst_id: str, company_id: str, title: str) -> PlacementDrive | None:
    return (
        db.query(PlacementDrive)
        .filter(
            PlacementDrive.institution_id == inst_id,
            PlacementDrive.company_id == company_id,
            PlacementDrive.title == title,
        )
        .first()
    )


def _ensure_drive(
    db: Session, inst_id: str, company_id: str, spec: dict, created_by: str
) -> PlacementDrive:
    existing = _drive_exists(db, inst_id, company_id, spec["title"])
    if existing:
        return existing

    drive = drive_service.create_drive(
        db,
        institution_id=inst_id,
        company_id=company_id,
        title=spec["title"],
        role_title=spec["role_title"],
        description=spec.get("description"),
        employment_type=spec.get("employment_type", "full_time"),
        location=spec.get("location"),
        ctc_lpa=spec.get("ctc_lpa"),
        stipend=spec.get("stipend"),
        apply_by=datetime.now(UTC) + timedelta(days=14),
        drive_date=datetime.now(UTC) + timedelta(days=30),
        status=spec.get("status", "draft"),
        criteria=spec["criteria"],
        required_skills=spec["required_skills"],
        created_by=created_by,
    )

    if spec.get("jd_pending"):
        drive.jd_text = spec["jd_text"]
        drive.jd_filename = "job-description.txt"
        drive.is_ai_extraction_pending = True

    if spec.get("rounds"):
        drive_service.replace_rounds(db, drive=drive, rounds=spec["rounds"])

    if drive.status == "published":
        drive_service.publish_drive(db, drive=drive)

    db.flush()
    return drive


def _advance_application_statuses(db: Session, inst_id: str) -> None:
    applications = (
        db.query(Application)
        .filter(Application.institution_id == inst_id, Application.status == "applied")
        .order_by(Application.applied_at)
        .all()
    )
    chain = ["in_review", "shortlisted", "interview", "offered"]
    service = ApplicationService(db)
    for index, app in enumerate(applications[:8]):
        # Walk the forward-only transition graph so every step is legal.
        for status in chain[: index % 4]:
            try:
                service.change_status(app.id, status, note="Seeded demo status.")
            except (PermissionError_, ValidationError):
                break


if __name__ == "__main__":
    main()