"""Shared test fixtures: isolated SQLite DB, seeding helpers, HTTP client.

Environment variables are set BEFORE importing any app module so the engine,
settings cache, and middleware are configured for the test run.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Generator
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = BACKEND_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = (
    "sqlite:///" + (BACKEND_DIR / "storage" / "test_placement.db").as_posix()
)
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["AI_ENABLED"] = "false"  # provider still falls back to offline heuristic
os.environ["SEED_ON_STARTUP"] = "false"
os.environ["SECRET_KEY"] = "test-only-secret-key-0123456789abcdef-0123456789"
os.environ["BCRYPT_ROUNDS"] = "4"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db import models as _models  # noqa: E402,F401  (registers mappers)
from app.db.base import Base  # noqa: E402
from app.db.models import (  # noqa: E402
    Company,
    Department,
    EligibilityCriterion,
    PlacementDrive,
    Student,
    User,
)
from app.db.session import SessionLocal, engine, get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import users as user_service  # noqa: E402
from app.services.students import provision_student  # noqa: E402

DEPT_CODE = "CSE"
INST_ID = settings.institution.code


@pytest.fixture(autouse=True)
def _reset_db() -> Generator[None, None, None]:
    """Fresh schema for every test; a leaked row cannot leak into the next."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    """TestClient whose get_db dependency yields the same test engine."""

    def _override_db() -> Generator[Session, None, None]:
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_db
    try:
        with TestClient(app) as c:
            yield c
    finally:
        app.dependency_overrides.pop(get_db, None)


class TestData:
    """Committed eagerly so request-scoped sessions see everything."""

    __test__ = False

    ADMIN_PASSWORD = "Admin@12345!"
    STUDENT_EMAIL = "student@test.example.edu"

    def __init__(self, db: Session) -> None:
        self.db = db

    def site(self) -> None:
        user_service.init_institution(self.db)
        for code, name in ((DEPT_CODE, "Computer Science"), ("ECE", "Electronics")):
            if (
                not self.db.query(Department)
                .filter(Department.institution_id == INST_ID, Department.code == code)
                .first()
            ):
                self.db.add(
                    Department(
                        institution_id=INST_ID,
                        code=code,
                        name=name,
                        is_technical=True,
                    )
                )
        self.db.commit()

    def admin(self, email: str = "admin@test.example.edu") -> tuple[str, User]:
        self.site()
        user = User(
            institution_id=INST_ID,
            email=email,
            password_hash=hash_password(self.ADMIN_PASSWORD),
            role="placement_admin",
            full_name="Test Admin",
            is_active=True,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return self._token(user), user

    def student(
        self,
        *,
        college_id: str = "1KS22CS001",
        email: str = STUDENT_EMAIL,
        full_name: str = "Test Student",
        cgpa: float | None = 8.4,
        batch_year: int = 2026,
        department_code: str = DEPT_CODE,
        backlogs: int = 0,
        active_backlogs: int = 0,
    ) -> tuple[str, Student]:
        self.site()
        user, student, _token = provision_student(
            self.db,
            institution_id=INST_ID,
            college_id=college_id,
            email=email,
            full_name=full_name,
            department_code=department_code,
            batch_year=batch_year,
            cgpa=cgpa,
            backlog_count=backlogs,
            active_backlogs=active_backlogs,
            academic_data_verified=True,
            send_activation=False,
        )
        self.db.commit()
        return self._token(user), student

    def pending_student(
        self,
        college_id: str = "1KS22CS002",
        email: str = "pending@test.example.edu",
    ) -> tuple[User, Student, str | None]:
        """Provision a student who still has to activate via token."""
        self.site()
        user, student, token = provision_student(
            self.db,
            institution_id=INST_ID,
            college_id=college_id,
            email=email,
            full_name="Pending Student",
            department_code=DEPT_CODE,
            batch_year=2026,
            cgpa=None,
            backlog_count=0,
            active_backlogs=0,
            academic_data_verified=True,
            send_activation=True,
        )
        self.db.commit()
        return user, student, token  # type: ignore[return-value]

    def company(self, name: str = "Acme Software") -> Company:
        self.site()
        row = Company(
            institution_id=INST_ID,
            name=name,
            website="https://acme.test",
            industry="software",
            contact_email="careers@acme.com",
            is_active=True,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def drive(
        self,
        company_id: str,
        *,
        title: str = "Software Engineering Intern",
        role_title: str = "SWE Intern",
        status: str = "draft",
        created_by: str | None = None,
    ) -> PlacementDrive:
        if created_by is None:
            _token, admin = self.admin()
            created_by = admin.id
        row = PlacementDrive(
            institution_id=INST_ID,
            company_id=company_id,
            title=title,
            role_title=role_title,
            status=status,
            created_by=created_by,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def criterion(self, drive_id: str, criterion_type: str, parameters: dict) -> None:
        self.db.add(
            EligibilityCriterion(
                institution_id=INST_ID,
                drive_id=drive_id,
                criterion_type=criterion_type,
                parameters=parameters,
                is_active=True,
            )
        )
        self.db.commit()

    @staticmethod
    def _token(user: User) -> str:
        return create_access_token(
            role=user.role, institution_id=user.institution_id, extra_claims={"sub": user.id}
        )


@pytest.fixture()
def seed() -> Generator[TestData, None, None]:
    db = SessionLocal()
    try:
        yield TestData(db)
    finally:
        db.close()


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
