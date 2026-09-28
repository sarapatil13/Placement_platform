"""Deterministic eligibility engine.

This module is the ONLY place eligibility is decided. No AI output can reach it.
Decisions are driven entirely by `EligibilityCriterion` rows that represent
confirmed institutional policy, read from the DB. Every rule returns a
machine-readable reason the UI can surface verbatim ("CGPA 6.8 < required 7.0").

Outcomes:
- "eligible"      — all active rules pass
- "ineligible"    — at least one active rule failed
- "inconclusive"  — data needed by a rule is missing on the student side

`inconclusive` is FEATURED: a blank CGPA must not silently pass a CGPA rule.
The admin decides whether a student with missing data may apply (by fixing data,
or adding a deliberate waiver rule); the engine never assumes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import (
    CRITERIA_AGE_MAX,
    CRITERIA_BACKLOG_MAX,
    CRITERIA_BATCH_YEARS,
    CRITERIA_CGPA_MAX,
    CRITERIA_CGPA_MIN,
    CRITERIA_DEPARTMENTS,
    CRITERIA_GENDER,
    CRITERIA_PERCENTILE_MIN,
    EligibilityCriterion,
    Student,
)

logger = get_logger("eligibility")

GENDER_VALUES = {"male", "female", "other"}


@dataclass
class RuleResult:
    criterion_type: str
    passed: bool
    decisive: bool  # True => this rule alone decides ineligible
    detail: str
    reason: str


@dataclass
class EligibilityVerdict:
    drive_id: str
    student_id: str
    eligible: bool
    definitive: bool  # False when data was missing (inconclusive)
    score: int = 0  # 0..100 aggregate, derived from passed/active rules
    reasons: list[str] = field(default_factory=list)  # exact, human-readable
    failed_rules: list[dict[str, object]] = field(default_factory=list)
    passed_rules: list[dict[str, object]] = field(default_factory=list)
    evaluated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def label(self) -> str:
        if not self.definitive:
            return "inconclusive"
        return "eligible" if self.eligible else "ineligible"


def _cgpa_ok(actual: float | None, threshold: float, kind: str) -> tuple[bool, bool, str]:
    if actual is None:
        return False, False, "CGPA is missing from institutional records; cannot verify the rule."
    scale = settings.institution.grading_scale_max or 10.0
    if actual > scale:
        return False, False, f"Recorded CGPA {actual} exceeds the institution scale ({scale})."
    if kind == "min":
        return (actual >= threshold, True,
                f"CGPA {actual} {'>= ' if actual >= threshold else '< '}{threshold} required")
    return (actual <= threshold, True,
            f"CGPA {actual} {'<= ' if actual <= threshold else '> '}{threshold} permitted")


def _backlog_ok(active: int | None, total: int | None, max_active: int | None, max_total: int | None) -> tuple[bool, bool, str]:
    if max_total is not None:
        if total is None:
            return False, False, "Backlog count is missing from institutional records."
        if total > max_total:
            return False, True, f"{total} total backlog(s) exceed the allowance ({max_total})."
    if max_active is not None:
        if active is None:
            return False, False, "Active backlog count is missing from institutional records."
        if active > max_active:
            return False, True, f"{active} active backlog(s) exceed the allowance ({max_active})."
    if max_active is not None and active == 0 and max_total is not None and total == 0:
        return True, True, "No active or standing backlogs."
    if max_active is not None and active == 0:
        return True, True, "No active backlogs."
    if max_total is not None and total == 0:
        return True, True, "No standing backlogs."
    return False, True, "Backlog policy not met."


def evaluate(
    db: Session,
    *,
    drive_id: str,
    student: Student,
    criteria: list[EligibilityCriterion] | None = None,
) -> EligibilityVerdict:
    criteria = criteria if criteria is not None else _load_active_criteria(db, drive_id)
    if not criteria:
        # No confirmed criteria => no constraints => eligible (nothing to fail).
        return EligibilityVerdict(
            drive_id=drive_id,
            student_id=student.id,
            eligible=True,
            definitive=True,
            score=100,
            reasons=["No eligibility criteria have been configured for this drive."],
            passed_rules=[],
            failed_rules=[],
        )

    results = [_evaluate_one(student, c) for c in criteria]
    failed = [r for r in results if not r.passed]
    missing_data = any(not r.decisive for r in failed)

    definitive = not missing_data
    eligible = len(failed) == 0
    score = _compute_score(results)

    reasons = []
    failed_rules = []
    passed_rules = []
    for r in results:
        entry: dict[str, object] = {
            "criterion_type": r.criterion_type,
            "passed": r.passed,
            "decisive": r.decisive,
            "detail": r.detail,
        }
        if r.passed:
            passed_rules.append(entry)
        else:
            failed_rules.append(entry)
            reasons.append(r.reason)

    if eligible:
        reasons = ["All confirmed eligibility criteria are satisfied.", *[r.reason for r in results]]
    else:
        prefix = "Data required to verify eligibility is incomplete." if missing_data \
            else "Not eligible for this opportunity."
        reasons = [prefix, *reasons]

    return EligibilityVerdict(
        drive_id=drive_id,
        student_id=student.id,
        eligible=eligible,
        definitive=definitive,
        score=score,
        reasons=reasons,
        failed_rules=failed_rules,
        passed_rules=passed_rules,
    )


def evaluate_for_admission(
    db: Session,
    *,
    drive_id: str,
    student: Student,
    criteria: list[EligibilityCriterion] | None = None,
) -> EligibilityVerdict:
    """Same engine, with a stricter consequence: missing data blocks the
    application outright. Students cannot apply while their record is
    inconclusive; the placement cell must fix the data first."""
    verdict = evaluate(db, drive_id=drive_id, student=student, criteria=criteria)
    if not verdict.definitive:
        verdict.eligible = False
        verdict.reasons = [
            "Your institutional academic record is incomplete. Contact the placement cell "
            "to have your data verified before applying.",
            *verdict.reasons,
        ]
    return verdict


def _load_active_criteria(db: Session, drive_id: str) -> list[EligibilityCriterion]:
    return (
        db.query(EligibilityCriterion)
        .filter(
            EligibilityCriterion.drive_id == drive_id,
            EligibilityCriterion.is_active.is_(True),
        )
        .all()
    )


def _compute_score(results: list[RuleResult]) -> int:
    if not results:
        return 100
    passed = sum(1 for r in results if r.passed)
    return round((passed / len(results)) * 100)


def _evaluate_one(student: Student, rule: EligibilityCriterion) -> RuleResult:
    kind = rule.criterion_type
    params = rule.parameters or {}

    if kind == CRITERIA_CGPA_MIN:
        threshold = _first_float(params, "value", "cgpa", default=None)
        if threshold is None:
            return _misconfigured(rule)
        ok, decisive, detail = _cgpa_ok(student.cgpa, threshold, "min")
        return RuleResult(
            kind, ok, decisive,
            detail,
            f"CGPA is < required minimum ({threshold})." if not ok and decisive else detail,
        )

    if kind == CRITERIA_CGPA_MAX:
        threshold = _first_float(params, "value", "cgpa", default=None)
        if threshold is None:
            return _misconfigured(rule)
        ok, decisive, detail = _cgpa_ok(student.cgpa, threshold, "max")
        return RuleResult(
            kind, ok, decisive,
            detail,
            f"CGPA exceeds the permitted maximum ({threshold})." if not ok and decisive else detail,
        )

    if kind == CRITERIA_BACKLOG_MAX:
        max_active = _first_int(params, "active_backlogs", "max_active_backlogs", default=None)
        max_total = _first_int(params, "backlogs", "max_backlogs", "total_backlogs", default=None)
        if max_active is None and max_total is None:
            # Backward-friendly: a lone numeric value means "no active backlogs".
            lone = _first_int(params, "value", "max", default=None)
            max_active = lone
        ok, decisive, detail = _backlog_ok(
            student.active_backlogs, student.backlog_count, max_active, max_total
        )
        return RuleResult(
            kind, ok, decisive, detail,
            f"Active backlog limit of {max_active} exceeded." if not ok and decisive and max_active is not None and (student.active_backlogs or 0) > max_active else
            f"Standing backlog limit of {max_total} exceeded." if not ok and decisive and max_total is not None and (student.backlog_count or 0) > max_total else
            detail,
        )

    if kind == CRITERIA_DEPARTMENTS:
        allowed = params.get("departments") or params.get("codes") or params.get("value")
        if isinstance(allowed, str):
            allowed = [a.strip() for a in allowed.split(",") if a.strip()]
        if not isinstance(allowed, list) or not allowed:
            return _misconfigured(rule)
        codes = {str(a).upper() for a in allowed}
        dept_code = student.department.code.upper() if student.department else ""
        ok = dept_code in codes
        return RuleResult(
            kind, ok, True,
            f"Department {dept_code or '?'} "
            f"is {'in' if ok else 'not in'} the eligible set {sorted(codes)}.",
            f"Your department ({dept_code or 'unknown'}) "
            f"is not eligible; allowed departments are {sorted(codes)}."
            if not ok else "Department is eligible.",
        )

    if kind == CRITERIA_BATCH_YEARS:
        years = params.get("years") or params.get("batch") or params.get("value")
        if isinstance(years, str):
            years = [int(y) for y in years.split(",") if y.strip().isdigit()]
        if not isinstance(years, list) or not years:
            return _misconfigured(rule)
        ok = student.batch_year in {int(y) for y in years}
        return RuleResult(
            kind, ok, True,
            f"Batch {student.batch_year} is {'in' if ok else 'not in'} the eligible set {sorted({int(y) for y in years})}.",
            f"Your batch ({student.batch_year}) is not eligible for this drive." if not ok else "Batch is eligible.",
        )

    if kind == CRITERIA_AGE_MAX:
        max_age = _first_int(params, "value", "age_max", default=None)
        if max_age is None or student.date_of_birth is None:
            return RuleResult(kind, False, False,
                              "Date of birth is missing on the student record; cannot verify age.",
                              "Date of birth missing; age cannot be verified.")
        age = _age_years(student.date_of_birth)
        ok = age <= max_age
        return RuleResult(
            kind, ok, True,
            f"Age {age} {'<= ' if ok else '> '}{max_age}.",
            f"Age {age} exceeds the permitted {max_age}." if not ok else "Age within limit.",
        )

    if kind == CRITERIA_GENDER:
        value = params.get("value")
        if value is None:
            return _misconfigured(rule)
        allowed = {str(value).lower()}
        if "both" in allowed or "all" in allowed:
            return RuleResult(
                kind, True, True,
                "Open to all genders.",
                "Gender policy is open to all.",
            )
        student_gender = (student.gender or "").lower()
        if not student_gender:
            return RuleResult(
                kind, False, False,
                "Gender not recorded on the student profile; cannot verify the policy.",
                "Gender not recorded; cannot verify this policy.",
            )
        ok = student_gender in allowed
        return RuleResult(
            kind, ok, True,
            f"Gender {student.gender} {'matches' if ok else 'does not match'} policy {sorted(allowed)}.",
            f"Gender {student.gender} is not within {sorted(allowed)}." if not ok else "Gender is eligible.",
        )

    if kind == CRITERIA_PERCENTILE_MIN:
        # Some programmes report percentile rather than CGPA; treat as soft gate
        # using the CGPA field only if the cell enters percentile into cgpa_source.
        threshold = _first_float(params, "value", "percentile", default=None)
        if threshold is None:
            return _misconfigured(rule)
        if student.cgpa is None:
            return RuleResult(kind, False, False,
                              "No CGPA/percentile recorded to evaluate the percentile gate.",
                              "Academic score missing; percentile cannot be evaluated.")
        ok, decisive, detail = _cgpa_ok(student.cgpa, threshold, "min")
        return RuleResult(kind, ok, decisive, detail, detail)

    _logger = logger.bind(drive_id=rule.drive_id, criterion_type=kind)
    _logger.warning("eligibility.unknown_criterion")
    return RuleResult(kind, False, False, "Unknown criterion type; treated as not satisfied.", "Unknown criterion.")


def _misconfigured(rule: EligibilityCriterion) -> RuleResult:
    logger.warning("eligibility.misconfigured_criterion", criterion_type=rule.criterion_type)
    return RuleResult(
        rule.criterion_type, False, True,
        "Criterion is missing required parameters; treated as failed.",
        f"Configuration error in {rule.criterion_type} rule; contact placement cell.",
    )


def _first_float(params: dict[str, object], *keys: str, default: float | None = None) -> float | None:
    from typing import Any, cast

    for k in keys:
        v = params.get(k)
        if v is None:
            continue
        try:
            return float(cast(Any, v))
        except (TypeError, ValueError):
            continue
    return default


def _first_int(params: dict[str, object], *keys: str, default: int | None = None) -> int | None:
    from typing import Any, cast

    for k in keys:
        v = params.get(k)
        if v is None:
            continue
        try:
            return int(cast(Any, v))
        except (TypeError, ValueError):
            continue
    return default


def _age_years(dob: date) -> int:
    today = datetime.utcnow().date()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


__all__ = ["EligibilityVerdict", "evaluate", "evaluate_for_admission"]