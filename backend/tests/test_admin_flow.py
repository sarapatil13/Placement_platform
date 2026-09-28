"""Placement-cell (admin) end-to-end flow: companies, imports, drives, JD, publish."""

from __future__ import annotations

from tests.conftest import TestData, auth_headers

from app.db.models import CRITERIA_CGPA_MIN

JD_TEXT = (
    "We are hiring a Python Developer for our Bengaluru office. "
    "Required skills: Python, Django, PostgreSQL. "
    "Minimum aggregate CGPA of 7.0. No active backlogs. "
    "Employment type: full_time."
)


def test_company_create_list_update_and_duplicate(seed: TestData, client) -> None:
    token, _admin = seed.admin()
    headers = auth_headers(token)
    payload = {
        "name": "Acme Software",
        "website": "https://acme.test",
        "industry": "software",
        "contact_email": "careers@acme.com",
    }

    created = client.post("/api/v1/admin/companies", json=payload, headers=headers)
    assert created.status_code == 200
    company_id = created.json()["id"]

    duplicate = client.post("/api/v1/admin/companies", json=payload, headers=headers)
    assert duplicate.status_code == 409
    assert duplicate.json()["code"] == "conflict"

    listing = client.get("/api/v1/admin/companies", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 1

    updated = client.patch(
        f"/api/v1/admin/companies/{company_id}",
        json={"industry": "software services"},
        headers=headers,
    )
    assert updated.status_code == 200
    assert updated.json()["industry"] == "software services"


def test_import_students_round_trip(seed: TestData, client) -> None:
    token, _admin = seed.admin()
    headers = auth_headers(token)
    resp = client.post(
        "/api/v1/admin/students/import",
        json={
            "send_activation": True,
            "students": [
                {
                    "college_id": "1KS22CS001",
                    "email": "s1@example.edu",
                    "full_name": "Student One",
                    "department_code": "CSE",
                    "batch_year": 2026,
                    "cgpa": 8.5,
                },
                {
                    "college_id": "1KS22CS002",
                    "email": "s2@example.edu",
                    "full_name": "Student Two",
                    "department_code": "CSE",
                    "batch_year": 2026,
                    "cgpa": 6.9,
                },
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["created"] == 2
    assert len(body["activation_tokens"]) == 2

    listing = client.get("/api/v1/admin/students", headers=headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 2


def test_import_is_skippable_on_conflict(seed: TestData, client) -> None:
    token, _admin = seed.admin()
    _s_token, student = seed.student()
    headers = auth_headers(token)
    resp = client.post(
        "/api/v1/admin/students/import",
        json={
            "send_activation": False,
            "students": [
                {
                    "college_id": student.college_id,
                    "email": "fresh@example.edu",
                    "full_name": "Fresh Student",
                    "department_code": "CSE",
                    "batch_year": 2026,
                    "cgpa": 8.0,
                }
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["created"] == 0
    assert resp.json()["skipped"] == 1


def test_full_drive_lifecycle(seed: TestData, client) -> None:
    token, _admin = seed.admin()
    headers = auth_headers(token)

    company_id = client.post(
        "/api/v1/admin/companies",
        json={"name": "Acme Software", "contact_email": "careers@acme.com"},
        headers=headers,
    ).json()["id"]

    client.post(
        "/api/v1/admin/students/import",
        json={
            "send_activation": False,
            "students": [
                {
                    "college_id": "1KS22CS001",
                    "email": "e1@example.edu",
                    "full_name": "Eligible Student",
                    "department_code": "CSE",
                    "batch_year": 2026,
                    "cgpa": 8.5,
                },
                {
                    "college_id": "1KS22CS002",
                    "email": "e2@example.edu",
                    "full_name": "Not Eligible Student",
                    "department_code": "CSE",
                    "batch_year": 2026,
                    "cgpa": 6.2,
                },
            ],
        },
        headers=headers,
    )

    criteria = [
        {"criterion_type": CRITERIA_CGPA_MIN, "parameters": {"value": 7.0}}
    ]
    created = client.post(
        "/api/v1/admin/drives",
        json={
            "company_id": company_id,
            "title": "Software Engineering Intern",
            "role_title": "Python Developer",
            "employment_type": "full_time",
            "status": "draft",
            "criteria": criteria,
            "required_skills": ["Python", "Django"],
        },
        headers=headers,
    )
    assert created.status_code == 200
    drive_id = created.json()["id"]

    uploaded = client.post(
        f"/api/v1/admin/drives/{drive_id}/jd",
        files={"file": ("jd.txt", JD_TEXT.encode(), "text/plain")},
        headers=headers,
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["needs_confirmation"] is True
    assert uploaded.json()["extracted"]["role_title"]

    evaluated = client.post(
        f"/api/v1/admin/drives/{drive_id}/eligibility/evaluate", headers=headers
    )
    assert evaluated.status_code == 200
    assert evaluated.json()["total"] == 2
    assert evaluated.json()["eligible"] == 1

    confirmed = client.post(
        f"/api/v1/admin/drives/{drive_id}/jd/confirm",
        json={"criteria": criteria, "required_skills": ["Python", "Django"]},
        headers=headers,
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["confirmed"] is True

    published = client.post(f"/api/v1/admin/drives/{drive_id}/publish", json={}, headers=headers)
    assert published.status_code == 200
    assert published.json()["status"] == "published"

    from app.db.models import Notification

    notified = (
        seed.db.query(Notification).filter(Notification.type == "new_drive").count()
    )
    assert notified == 1


def test_invalid_department_rejected_on_import(seed: TestData, client) -> None:
    token, _admin = seed.admin()
    headers = auth_headers(token)
    resp = client.post(
        "/api/v1/admin/students/import",
        json={
            "send_activation": False,
            "students": [
                {
                    "college_id": "1KS22CS099",
                    "email": "ghost@example.edu",
                    "full_name": "Ghost Student",
                    "department_code": "MARINE",
                    "batch_year": 2026,
                    "cgpa": 8.0,
                }
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 404
    assert resp.json()["code"] == "not_found"
