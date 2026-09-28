"""End-to-end journeys over the real HTTP API.

These exercises the full stack — auth, institution, drives, eligibility,
applications, notifications, and analytics — the way the SPA consumes it.
They reuse the same TestClient / TestData fixtures as the rest of the suite.
"""

from __future__ import annotations

import pymupdf
from tests.conftest import auth_headers

CRITERIA = [
    {"criterion_type": "cgpa_min", "parameters": {"value": 7.0}},
    {"criterion_type": "backlog_max", "parameters": {"active_backlogs": 0}},
    {"criterion_type": "departments", "parameters": {"departments": ["CSE", "ECE"]}},
    {"criterion_type": "batch_years", "parameters": {"years": [2026, 2027]}},
]
SKILLS = ["python", "sql", "data structures", "git"]


def _make_pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _upload_resume(client, token: str, text: str):
    payload = _make_pdf(text)
    resp = client.post(
        "/api/v1/resumes",
        headers=auth_headers(token),
        files={"file": ("resume.pdf", payload, "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["resume"]


def _make_drive(client, admin_token: str, company_id: str) -> str:
    resp = client.post(
        "/api/v1/admin/drives",
        headers=auth_headers(admin_token),
        json={
            "company_id": company_id,
            "title": "Software Engineering Trainee",
            "role_title": "SWE Trainee",
            "description": "Work on the campus placement portal.",
            "employment_type": "full_time",
            "location": "Hubballi",
            "ctc_lpa": "8.0",
            "criteria": CRITERIA,
            "required_skills": SKILLS,
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def test_full_student_and_admin_journey(client, seed):
    admin_token, _admin = seed.admin()
    student_token, _student = seed.student(
        full_name="Aarav Sharma", cgpa=8.6, batch_year=2026, backlogs=0, active_backlogs=0
    )

    # Admin: register a company.
    comp = client.post(
        "/api/v1/admin/companies",
        headers=auth_headers(admin_token),
        json={"name": "Nimbus Cloud", "contact_email": "careers@nimbus.example.com", "industry": "software"},
    )
    assert comp.status_code == 200, comp.text
    company_id = comp.json()["id"]

    # Admin: create + publish a drive.
    drive_id = _make_drive(client, admin_token, company_id)
    pub = client.post(f"/api/v1/admin/drives/{drive_id}/publish", headers=auth_headers(admin_token), json={})
    assert pub.status_code == 200, pub.text
    assert pub.json()["status"] == "published"

    # Student: sees the drive in the open list.
    listing = client.get("/api/v1/drives", headers=auth_headers(student_token))
    assert listing.status_code == 200
    assert any(d["id"] == drive_id for d in listing.json()["items"])

    # Student: eligibility check passes.
    elig = client.get(f"/api/v1/drives/{drive_id}/eligibility", headers=auth_headers(student_token))
    assert elig.status_code == 200, elig.text
    assert elig.json()["eligible"] is True, elig.json()

    # Student: uploads a resume (primary), then applies.
    resume = _upload_resume(
        client, student_token, "Aarav Sharma\nPython, SQL, data structures, git, fastapi"
    )
    app = client.post(
        "/api/v1/applications",
        headers=auth_headers(student_token),
        json={"drive_id": drive_id, "resume_id": resume["id"], "cover_note": "Eager to learn."},
    )
    assert app.status_code == 201, app.text
    assert app.json()["status"] == "applied"
    application_id = app.json()["id"]

    # Student: application appears with detail + history.
    mine = client.get("/api/v1/applications/me", headers=auth_headers(student_token))
    assert mine.status_code == 200
    assert any(a["id"] == application_id for a in mine.json())

    detail = client.get(f"/api/v1/applications/{application_id}", headers=auth_headers(student_token))
    assert detail.status_code == 200
    assert detail.json()["resume_filename"].endswith(".pdf")
    assert detail.json()["status_history"][0]["to_status"] == "applied"
    snap = detail.json()["eligibility_snapshot"]
    assert snap["eligible"] is True

    # Admin: sees the application and advances it to in_review.
    admin_apps = client.get(
        "/api/v1/admin/applications",
        headers=auth_headers(admin_token),
        params={"drive_id": drive_id},
    )
    assert admin_apps.status_code == 200
    assert admin_apps.json()["total"] == 1

    moved = client.patch(
        f"/api/v1/admin/applications/{application_id}/status",
        headers=auth_headers(admin_token),
        json={"new_status": "in_review", "note": "Shortlisted for screening"},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["status"] == "in_review"

    # Student: gets a real-time notification for the move.
    notifs = client.get("/api/v1/notifications", headers=auth_headers(student_token))
    assert notifs.status_code == 200
    assert notifs.json()["unread_count"] >= 1
    types = {n["type"] for n in notifs.json()["items"]}
    assert "status_change" in types

    # Admin: analytics reflect the application.
    summary = client.get("/api/v1/admin/analytics/summary", headers=auth_headers(admin_token))
    assert summary.status_code == 200
    body = summary.json()
    assert body["total_applications"] >= 1
    assert body["unique_applicants"] >= 1
    assert any(d["drive_id"] == drive_id for d in body["top_drives"])

    # Student notifications page supports mark-all-read.
    mark = client.post("/api/v1/notifications/mark-read", headers=auth_headers(student_token), json={"ids": None})
    assert mark.status_code == 200


def test_ineligible_student_cannot_apply(client, seed):
    admin_token, _admin = seed.admin()
    low_token, _low = seed.student(
        full_name="Low CGPA", cgpa=5.1, batch_year=2026, backlogs=2, active_backlogs=1
    )
    good_token, _good = seed.student(
        college_id="1KS22CS010",
        email="good@test.example.edu",
        full_name="Good Student",
        cgpa=8.2,
        batch_year=2026,
    )
    comp = client.post(
        "/api/v1/admin/companies",
        headers=auth_headers(admin_token),
        json={"name": "DataWeave", "contact_email": "jobs@dataweave.example.com"},
    )
    drive_id = _make_drive(client, admin_token, comp.json()["id"])
    client.post(f"/api/v1/admin/drives/{drive_id}/publish", headers=auth_headers(admin_token), json={})

    low_elig = client.get(f"/api/v1/drives/{drive_id}/eligibility", headers=auth_headers(low_token))
    assert low_elig.status_code == 200
    assert low_elig.json()["eligible"] is False

    low_app = client.post(
        "/api/v1/applications",
        headers=auth_headers(low_token),
        json={"drive_id": drive_id},
    )
    assert low_app.status_code == 403, low_app.text

    # A compliant student succeeds in the same drive.
    good_app = client.post(
        "/api/v1/applications",
        headers=auth_headers(good_token),
        json={"drive_id": drive_id, "cover_note": "I meet all criteria."},
    )
    assert good_app.status_code == 201, good_app.text

    # ...but not twice (dedupe).
    dup = client.post(
        "/api/v1/applications",
        headers=auth_headers(good_token),
        json={"drive_id": drive_id},
    )
    assert dup.status_code == 409, dup.text


def test_student_withdraws_application(client, seed):
    admin_token, _admin = seed.admin()
    token, _student = seed.student(full_name="Withdrawer", cgpa=8.9, batch_year=2026)
    comp = client.post(
        "/api/v1/admin/companies",
        headers=auth_headers(admin_token),
        json={"name": "SecureGrid", "contact_email": "hr@securegrid.example.com"},
    )
    drive_id = _make_drive(client, admin_token, comp.json()["id"])
    client.post(f"/api/v1/admin/drives/{drive_id}/publish", headers=auth_headers(admin_token), json={})

    app = client.post(
        "/api/v1/applications",
        headers=auth_headers(token),
        json={"drive_id": drive_id, "cover_note": "Interested in security."},
    )
    assert app.status_code == 201, app.text
    application_id = app.json()["id"]

    withdrawn = client.post(
        f"/api/v1/applications/{application_id}/withdraw",
        headers=auth_headers(token),
        json={"reason": "Accepted another offer"},
    )
    assert withdrawn.status_code == 200, withdrawn.text
    assert withdrawn.json()["status"] == "withdrawn"
    assert withdrawn.json()["withdrawn_reason"] == "Accepted another offer"

    # Withdrawing again is an invalid transition.
    again = client.post(
        f"/api/v1/applications/{application_id}/withdraw",
        headers=auth_headers(token),
        json={},
    )
    assert again.status_code > 400, again.text