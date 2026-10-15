"""Drive rounds: admin CRUD, student visibility, tenant isolation, roadmap focus."""

from __future__ import annotations

from tests.conftest import INST_ID, auth_headers

from app.db.models import Company, Institution, PlacementDrive, Resume
from app.services import drives as drive_service
from app.services.resumes import build_prep_roadmap


def _rounds(*specs: tuple[str, str, list[str]]) -> list[dict]:
    return [
        {"position": i + 1, "round_type": rt, "title": title, "topics": topics}
        for i, (rt, title, topics) in enumerate(specs)
    ]


def test_admin_replaces_rounds_and_student_reads_them(client, seed) -> None:
    admin_token, _admin = seed.admin()
    student_token, _student = seed.student()
    company = seed.company()
    drive = seed.drive(company.id, status="published")

    payload = _rounds(
        ("online_assessment", "Online Assessment", ["python", "sql"]),
        ("technical_interview", "Technical Interview", ["pandas"]),
    )
    resp = client.put(
        f"/api/v1/admin/drives/{drive.id}/rounds",
        json={"rounds": payload},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 200, resp.text
    assert [r["round_type"] for r in resp.json()["rounds"]] == [
        "online_assessment",
        "technical_interview",
    ]
    assert [r["position"] for r in resp.json()["rounds"]] == [1, 2]

    listing = client.get(
        f"/api/v1/admin/drives/{drive.id}/rounds", headers=auth_headers(admin_token)
    )
    assert listing.status_code == 200
    assert len(listing.json()["rounds"]) == 2

    # Replace semantics: submitting one round removes the others.
    replaced = client.put(
        f"/api/v1/admin/drives/{drive.id}/rounds",
        json={"rounds": _rounds(("hr_interview", "HR", ["communication"]))},
        headers=auth_headers(admin_token),
    )
    assert replaced.status_code == 200
    assert len(replaced.json()["rounds"]) == 1

    student_view = client.get(
        f"/api/v1/drives/{drive.id}/rounds", headers=auth_headers(student_token)
    )
    assert student_view.status_code == 200
    assert [r["round_type"] for r in student_view.json()] == ["hr_interview"]


def test_student_cannot_see_rounds_of_draft_drive(client, seed) -> None:
    _admin_token, _admin = seed.admin()
    student_token, _student = seed.student()
    company = seed.company()
    drive = seed.drive(company.id, status="draft")

    resp = client.get(
        f"/api/v1/drives/{drive.id}/rounds", headers=auth_headers(student_token)
    )
    assert resp.status_code == 404


def test_invalid_round_type_rejected(client, seed) -> None:
    admin_token, _admin = seed.admin()
    company = seed.company()
    drive = seed.drive(company.id)

    resp = client.put(
        f"/api/v1/admin/drives/{drive.id}/rounds",
        json={"rounds": _rounds(("bogus", "Mystery round", []))},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 422


def test_duplicate_round_position_rejected(client, seed) -> None:
    admin_token, _admin = seed.admin()
    company = seed.company()
    drive = seed.drive(company.id)

    payload = [
        {"position": 1, "round_type": "online_assessment", "title": "OA", "topics": []},
        {"position": 1, "round_type": "hr_interview", "title": "HR", "topics": []},
    ]
    resp = client.put(
        f"/api/v1/admin/drives/{drive.id}/rounds",
        json={"rounds": payload},
        headers=auth_headers(admin_token),
    )
    assert resp.status_code == 422


def test_rounds_are_tenant_scoped(client, seed) -> None:
    admin_token, admin = seed.admin()
    student_token, _student = seed.student()

    other = Institution(
        name="Other College",
        short_name="OC",
        code="OTHER",
        contact_email="office@other.example.edu",
        identity_issuer="other",
    )
    seed.db.add(other)
    seed.db.commit()
    seed.db.refresh(other)
    other_company = Company(
        institution_id=other.id,
        name="Other Corp",
        contact_email="hr@other.example.com",
        is_active=True,
    )
    seed.db.add(other_company)
    seed.db.commit()
    seed.db.refresh(other_company)
    other_drive = PlacementDrive(
        institution_id=other.id,
        company_id=other_company.id,
        title="Other Drive",
        role_title="Other Role",
        status="published",
        created_by=admin.id,
    )
    seed.db.add(other_drive)
    seed.db.commit()
    seed.db.refresh(other_drive)

    admin_attempt = client.put(
        f"/api/v1/admin/drives/{other_drive.id}/rounds",
        json={"rounds": _rounds(("hr_interview", "HR", []))},
        headers=auth_headers(admin_token),
    )
    assert admin_attempt.status_code == 404

    student_attempt = client.get(
        f"/api/v1/drives/{other_drive.id}/rounds", headers=auth_headers(student_token)
    )
    assert student_attempt.status_code == 404


def test_roadmap_includes_rounds_with_focus_skills(seed) -> None:
    _admin_token, admin = seed.admin()
    _student_token, student = seed.student()
    company = seed.company()

    drive = drive_service.create_drive(
        seed.db,
        institution_id=INST_ID,
        company_id=company.id,
        title="Data Analyst",
        role_title="Data Analyst",
        description=None,
        employment_type="full_time",
        location=None,
        ctc_lpa=None,
        stipend=None,
        apply_by=None,
        drive_date=None,
        status="published",
        criteria=[],
        required_skills=["python", "sql", "pandas"],
        created_by=admin.id,
    )
    drive_service.replace_rounds(
        seed.db,
        drive=drive,
        rounds=_rounds(
            ("online_assessment", "Online Assessment", ["sql", "aptitude"]),
            ("technical_interview", "Technical Interview", ["pandas", "communication"]),
        ),
    )

    seed.db.add(
        Resume(
            institution_id=INST_ID,
            student_id=student.id,
            filename="resume.pdf",
            storage_path="resume.pdf",
            mime_type="application/pdf",
            size_bytes=10,
            sha256="a" * 64,
            parse_status="parsed",
            is_primary=True,
            parsed_skills=["python"],
        )
    )
    seed.db.commit()

    roadmap = build_prep_roadmap(seed.db, student=student, drive_id=drive.id)
    assert len(roadmap["rounds"]) == 2
    by_type = {r["round_type"]: r for r in roadmap["rounds"]}
    assert by_type["online_assessment"]["focus_skills"] == ["sql"]
    assert by_type["technical_interview"]["focus_skills"] == ["pandas"]
