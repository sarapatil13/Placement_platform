"""RBAC enforcement tests: role isolation across admin/student surfaces."""

from __future__ import annotations

from tests.conftest import TestData, auth_headers


def test_unauthenticated_request_blocked(seed: TestData, client) -> None:
    resp = client.get("/api/v1/drives")
    assert resp.status_code == 401


def test_student_cannot_read_admin_students(seed: TestData, client) -> None:
    token, _student = seed.student()
    resp = client.get("/api/v1/admin/students", headers=auth_headers(token))
    assert resp.status_code == 403
    assert resp.json()["code"] == "insufficient_permissions"


def test_student_cannot_manage_companies(seed: TestData, client) -> None:
    token, _student = seed.student()
    resp = client.post(
        "/api/v1/admin/companies",
        json={"name": "Nope", "contact_email": "nope@example.edu"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403


def test_admin_can_list_students(seed: TestData, client) -> None:
    admin_token, _admin = seed.admin()
    _s_token, student = seed.student()

    resp = client.get("/api/v1/admin/students", headers=auth_headers(admin_token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["college_id"] == student.college_id


def test_admin_cannot_use_student_only_eligibility(seed: TestData, client) -> None:
    admin_token, _admin = seed.admin()
    company = seed.company()
    drive = seed.drive(company.id)
    seed.criterion(drive.id, "cgpa_min", {"value": 7.0})

    resp = client.get(
        f"/api/v1/drives/{drive.id}/eligibility", headers=auth_headers(admin_token)
    )
    assert resp.status_code == 403
    assert resp.json()["code"] == "student_only"


def test_drive_from_another_tenant_is_hidden(seed: TestData, client) -> None:
    from app.core.config import settings
    from app.db.models import Institution, PlacementDrive

    _admin_token, _admin = seed.admin()
    company = seed.company()
    other = Institution(
        id="OTHER",
        name="Other University",
        short_name="OU",
        code="OTHER",
        contact_email="ou@example.com",
        grading_scale_max=10.0,
        identity_issuer=settings.institution.identity_issuer,
    )
    seed.db.add(other)
    seed.db.commit()

    foreign = PlacementDrive(
        institution_id="OTHER",
        company_id=company.id,
        title="Foreign drive",
        role_title="Foreign",
        status="published",
        created_by=_admin.id,
    )
    seed.db.add(foreign)
    seed.db.commit()

    token, _student = seed.student()
    listing = client.get("/api/v1/drives", headers=auth_headers(token))
    assert listing.status_code == 200
    assert listing.json()["total"] == 0