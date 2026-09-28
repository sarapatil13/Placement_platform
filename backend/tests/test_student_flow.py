"""Student-facing flow: view drives, eligibility check, apply, withdrawals."""

from __future__ import annotations

from tests.conftest import TestData, auth_headers

from app.db.models import CRITERIA_CGPA_MIN


def _published_drive(seed: TestData, client, headers: dict, company_id: str) -> str:
    criteria = [{"criterion_type": CRITERIA_CGPA_MIN, "parameters": {"value": 7.0}}]
    created = client.post(
        "/api/v1/admin/drives",
        json={
            "company_id": company_id,
            "title": "Software Engineering Intern",
            "role_title": "SWE Intern",
            "status": "draft",
            "criteria": criteria,
            "required_skills": ["Python"],
        },
        headers=headers,
    )
    drive_id = created.json()["id"]
    confirmed = client.post(
        f"/api/v1/admin/drives/{drive_id}/jd/confirm",
        json={"criteria": criteria, "required_skills": ["Python"]},
        headers=headers,
    )
    assert confirmed.status_code == 200
    published = client.post(
        f"/api/v1/admin/drives/{drive_id}/publish", json={}, headers=headers
    )
    assert published.status_code == 200
    return drive_id


def test_student_views_catalog(seed: TestData, client) -> None:
    admin_token, _admin = seed.admin()
    admin_headers = auth_headers(admin_token)
    company_id = client.post(
        "/api/v1/admin/companies",
        json={"name": "Acme Software", "contact_email": "careers@acme.com"},
        headers=admin_headers,
    ).json()["id"]
    _published_drive(seed, client, admin_headers, company_id)

    student_token, _student = seed.student()
    listing = client.get("/api/v1/drives", headers=auth_headers(student_token))
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["title"] == "Software Engineering Intern"


def test_student_applies_and_then_withdraws(seed: TestData, client) -> None:
    admin_token, _admin = seed.admin()
    admin_headers = auth_headers(admin_token)
    company_id = client.post(
        "/api/v1/admin/companies",
        json={"name": "Acme Software", "contact_email": "careers@acme.com"},
        headers=admin_headers,
    ).json()["id"]
    drive_id = _published_drive(seed, client, admin_headers, company_id)

    student_token, _student = seed.student(cgpa=8.4)
    student_headers = auth_headers(student_token)

    check = client.get(
        f"/api/v1/drives/{drive_id}/eligibility", headers=student_headers
    )
    assert check.status_code == 200
    assert check.json()["eligible"] is True

    applied = client.post(
        "/api/v1/applications",
        json={"drive_id": drive_id, "cover_note": "Excited to apply."},
        headers=student_headers,
    )
    assert applied.status_code == 201
    application_id = applied.json()["id"]
    assert applied.json()["status"] == "applied"

    duplicate = client.post(
        "/api/v1/applications",
        json={"drive_id": drive_id},
        headers=student_headers,
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "duplicate_application"

    mine = client.get("/api/v1/applications/me", headers=student_headers)
    assert mine.status_code == 200
    assert len(mine.json()) == 1

    withdrawn = client.post(
        f"/api/v1/applications/{application_id}/withdraw",
        json={"reason": "Found a better offer"},
        headers=student_headers,
    )
    assert withdrawn.status_code == 200
    assert withdrawn.json()["status"] == "withdrawn"


def test_ineligible_student_is_blocked(seed: TestData, client) -> None:
    admin_token, _admin = seed.admin()
    admin_headers = auth_headers(admin_token)
    company_id = client.post(
        "/api/v1/admin/companies",
        json={"name": "Acme Software", "contact_email": "careers@acme.com"},
        headers=admin_headers,
    ).json()["id"]
    drive_id = _published_drive(seed, client, admin_headers, company_id)

    student_token, _student = seed.student(cgpa=6.2)
    student_headers = auth_headers(student_token)

    check = client.get(
        f"/api/v1/drives/{drive_id}/eligibility", headers=student_headers
    )
    assert check.status_code == 200
    assert check.json()["eligible"] is False

    applied = client.post(
        "/api/v1/applications",
        json={"drive_id": drive_id},
        headers=student_headers,
    )
    assert applied.status_code == 403
    assert applied.json()["code"] == "not_eligible"
    assert applied.json()["reasons"]


def test_cannot_apply_to_draft_drive(seed: TestData, client) -> None:
    admin_token, _admin = seed.admin()
    admin_headers = auth_headers(admin_token)
    company_id = client.post(
        "/api/v1/admin/companies",
        json={"name": "Acme Software", "contact_email": "careers@acme.com"},
        headers=admin_headers,
    ).json()["id"]
    created = client.post(
        "/api/v1/admin/drives",
        json={"company_id": company_id, "title": "Draft role", "role_title": "Draft"},
        headers=admin_headers,
    )
    drive_id = created.json()["id"]

    student_token, _student = seed.student()
    applied = client.post(
        "/api/v1/applications",
        json={"drive_id": drive_id},
        headers=auth_headers(student_token),
    )
    assert applied.status_code == 422
    assert applied.json()["code"] == "drive_not_open"
