"""Eligibility engine tests: CGPA, backlog, department, inconclusive data."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from tests.conftest import TestData

from app.db.models import (
    CRITERIA_BACKLOG_MAX,
    CRITERIA_CGPA_MIN,
    CRITERIA_DEPARTMENTS,
)
from app.db.models import Student as StudentRow
from app.services.eligibility import evaluate, evaluate_for_admission


@dataclass
class StudentIn:
    college_id: str
    email: str
    cgpa: float | None
    backlogs: int = 0
    active_backlogs: int = 0
    department_code: str = "CSE"
    batch_year: int = 2026


def _provision(seed: TestData, s: StudentIn) -> StudentRow:
    seed.site()
    _token, student_row = seed.student(
        college_id=s.college_id,
        email=s.email,
        cgpa=s.cgpa,
        backlogs=s.backlogs,
        active_backlogs=s.active_backlogs,
        department_code=s.department_code,
        batch_year=s.batch_year,
    )
    return student_row


def _verdict(seed: TestData, student_row: StudentRow, drive_id: str):
    return evaluate(seed.db, drive_id=drive_id, student=student_row)


ELIGIBLE = StudentIn("1KS22CS001", "a@example.edu", 8.4)
TOO_LOW = StudentIn("1KS22CS002", "b@example.edu", 6.2)
MISSING = StudentIn("1KS22CS003", "c@example.edu", None)
HAS_BACKLOG = StudentIn("1KS22CS004", "d@example.edu", 8.4, backlogs=0, active_backlogs=2)
ECE_STUDENT = StudentIn("1KS22EC005", "e@example.edu", 8.4, department_code="ECE")


def test_cgpa_min_rule_passes_and_fails(seed: TestData) -> None:
    drive = seed.drive(company_id=seed.company().id)
    seed.criterion(drive.id, CRITERIA_CGPA_MIN, {"value": 7.0})

    ok = _verdict(seed, _provision(seed, ELIGIBLE), drive.id)
    assert ok.eligible is True
    assert ok.definitive is True
    assert ok.label == "eligible"

    low = _verdict(seed, _provision(seed, TOO_LOW), drive.id)
    assert low.eligible is False
    assert low.definitive is True
    assert any("CGPA" in r for r in low.reasons)


def test_missing_cgpa_is_inconclusive_never_eligible(seed: TestData) -> None:
    drive = seed.drive(company_id=seed.company().id)
    seed.criterion(drive.id, CRITERIA_CGPA_MIN, {"value": 7.0})

    pending = _verdict(seed, _provision(seed, MISSING), drive.id)
    assert pending.eligible is False
    assert pending.definitive is False
    assert pending.label == "inconclusive"


def test_backlog_rule(seed: TestData) -> None:
    drive = seed.drive(company_id=seed.company().id)
    seed.criterion(drive.id, CRITERIA_BACKLOG_MAX, {"active_backlogs": 0})

    with_backlog = _verdict(seed, _provision(seed, HAS_BACKLOG), drive.id)
    assert with_backlog.eligible is False
    assert with_backlog.definitive is True

    clean = _verdict(seed, _provision(seed, ELIGIBLE), drive.id)
    assert clean.eligible is True


def test_department_rule(seed: TestData) -> None:
    drive = seed.drive(company_id=seed.company().id)
    seed.criterion(drive.id, CRITERIA_DEPARTMENTS, {"departments": ["CSE"]})

    in_dept = _verdict(seed, _provision(seed, ELIGIBLE), drive.id)
    assert in_dept.eligible is True

    out_dept = _verdict(seed, _provision(seed, ECE_STUDENT), drive.id)
    assert out_dept.eligible is False
    assert out_dept.definitive is True
    assert any("department" in r.lower() for r in out_dept.reasons)


def test_no_criteria_is_unconditional_eligible(seed: TestData) -> None:
    drive = seed.drive(company_id=seed.company().id)
    verdict = _verdict(seed, _provision(seed, ELIGIBLE), drive.id)
    assert verdict.eligible is True
    assert verdict.definitive is True
    assert any("criteria" in r.lower() for r in verdict.reasons)


def test_admission_gate_blocks_inconclusive(seed: TestData) -> None:
    drive = seed.drive(company_id=seed.company().id)
    seed.criterion(drive.id, CRITERIA_CGPA_MIN, {"value": 7.0})

    student_row = _provision(seed, MISSING)
    verdict = evaluate_for_admission(seed.db, drive_id=drive.id, student=student_row)
    assert verdict.eligible is False
    assert any("incomplete" in r for r in verdict.reasons)


@pytest.mark.parametrize(
    "cgpa,threshold,expected",
    [(9.1, 9.0, True), (9.0, 9.1, False)],
)
def test_cgpa_boundary(seed: TestData, cgpa: float, threshold: float, expected: bool) -> None:
    drive = seed.drive(company_id=seed.company().id)
    seed.criterion(drive.id, CRITERIA_CGPA_MIN, {"value": threshold})
    student_row = _provision(seed, StudentIn("1KS22CS007", "f@example.edu", cgpa))
    verdict = _verdict(seed, student_row, drive.id)
    assert verdict.eligible is expected