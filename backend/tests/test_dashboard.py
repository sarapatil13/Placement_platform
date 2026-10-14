"""Student dashboard aggregation and lazy deadline reminders."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tests.conftest import INST_ID, auth_headers

from app.db.models import APP_APPLIED, Application, DriveSkill, Skill

BASE = "/api/v1/students/me/dashboard"


def _set_deadline(seed, drive, *, hours: float) -> None:
    drive.apply_by = datetime.now(UTC) + timedelta(hours=hours)
    seed.db.commit()


def test_dashboard_lists_eligible_open_drives(client, seed) -> None:
    token, _student = seed.student()
    company = seed.company()
    drive = seed.drive(company.id, status="published")
    _set_deadline(seed, drive, hours=240)

    resp = client.get(BASE, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    assert [d["drive_id"] for d in resp.json()["eligible_open_drives"]] == [drive.id]
    item = resp.json()["eligible_open_drives"][0]
    assert item["company_name"] == company.name
    assert item["days_left"] is not None and 9.9 <= resp.json()["eligible_open_drives"][0]["days_left"] <= 10.1
    assert resp.json()["closing_soon"] == []
    assert resp.json()["total_applications"] == 0
    assert resp.json()["application_counts_by_status"] == {}
    assert resp.json()["top_skill_gaps"] == []


def test_deadline_reminder_created_once_and_closing_soon(client, seed) -> None:
    token, _student = seed.student()
    company = seed.company()
    drive = seed.drive(company.id, status="published")
    _set_deadline(seed, drive, hours=12)

    resp = client.get(BASE, headers=auth_headers(token))
    assert resp.status_code == 200
    assert [d["drive_id"] for d in resp.json()["closing_soon"]] == [drive.id]

    first = client.get("/api/v1/notifications", headers=auth_headers(token))
    assert first.status_code == 200
    reminders = [n for n in first.json()["items"] if n["type"] == "deadline_soon"]
    assert len(reminders) == 1
    assert reminders[0]["payload"]["drive_id"] == drive.id

    # Idempotent: a second read does not duplicate the reminder.
    second = client.get("/api/v1/notifications", headers=auth_headers(token))
    reminders = [n for n in second.json()["items"] if n["type"] == "deadline_soon"]
    assert len(reminders) == 1


def test_dashboard_excludes_ineligible_and_applied_drives(client, seed) -> None:
    token, student = seed.student()
    company = seed.company()

    open_drive = seed.drive(company.id, title="Open Role", status="published")
    _set_deadline(seed, open_drive, hours=240)

    gated = seed.drive(company.id, title="Gated Role", status="published")
    _set_deadline(seed, gated, hours=240)
    seed.criterion(gated.id, "cgpa_min", {"value": 9.9})

    applied = seed.drive(company.id, title="Applied Role", status="published")
    _set_deadline(seed, applied, hours=240)
    seed.db.add(
        Application(
            institution_id=INST_ID,
            student_id=student.id,
            drive_id=applied.id,
            status=APP_APPLIED,
            eligibility_snapshot={},
        )
    )
    seed.db.commit()

    resp = client.get(BASE, headers=auth_headers(token))
    assert resp.status_code == 200
    titles = {d["title"] for d in resp.json()["eligible_open_drives"]}
    assert titles == {"Open Role"}
    assert resp.json()["total_applications"] == 1
    assert resp.json()["application_counts_by_status"][APP_APPLIED] == 1


def test_dashboard_reports_top_skill_gaps(client, seed) -> None:
    token, _student = seed.student()
    company = seed.company()
    drive = seed.drive(company.id, status="published")
    _set_deadline(seed, drive, hours=240)

    for name in ("Python", "Docker"):
        skill = Skill(institution_id=INST_ID, name=name, normalized_name=name.lower())
        seed.db.add(skill)
        seed.db.commit()
        seed.db.add(
            DriveSkill(institution_id=INST_ID, drive_id=drive.id, skill_id=skill.id)
        )
        seed.db.commit()

    resp = client.get(BASE, headers=auth_headers(token))
    assert resp.status_code == 200
    gaps = {g["skill"]: g["drives"] for g in resp.json()["top_skill_gaps"]}
    assert gaps == {"Python": 1, "Docker": 1}


def test_dashboard_requires_student(client, seed) -> None:
    admin_token, _admin = seed.admin()
    resp = client.get(BASE, headers=auth_headers(admin_token))
    assert resp.status_code == 403
