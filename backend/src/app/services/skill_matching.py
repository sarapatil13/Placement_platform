"""Deterministic, code-only skill matching.

Used for both resume-JD matching and JD-vs-student matching. AI may suggest a
skill list; the *classification* into matched/partial/missing is always this code.

Fuzzy rules are intentionally simple and transparent (no ML): a student's skill
counts as ::matched:: when it contains the required skill, and as ::partial:: when
they share four or more leading characters. The result is deterministic and unit
tested.
"""

from __future__ import annotations

from collections.abc import Iterable

PartialsResult = tuple[set[str], set[str], set[str]]


def normalize(skill: str) -> str:
    return skill.strip().lower().replace(".", "").replace("-", " ")


def match_skills(resume_skills: Iterable[str], required: Iterable[str]) -> PartialsResult:
    """Return (matched, partial, missing) relative to the required set."""
    resume_norm = {normalize(s) for s in resume_skills if s}
    required_norm = {normalize(s) for s in required if s}

    matched: set[str] = set()
    partial: set[str] = set()
    missing: set[str] = set()

    for req in required_norm:
        if req in resume_norm:
            matched.add(req.lstrip().lower())
            continue
        # Partial: the student lists a superset or a near-spelling of the skill.
        found_partial = False
        for have in resume_norm:
            if req in have and len(req) >= 4:
                matched.add(req)
                found_partial = True
                break
            if _closeness(req, have) and len(req) >= 5:
                partial.add(req)
                found_partial = True
                break
        if found_partial:
            continue
        missing.add(req)

    return matched, partial, missing


def _closeness(a: str, b: str, min_overlap: int = 4) -> bool:
    a_bits = set(a)
    b_bits = set(b)
    if len(a_bits) < min_overlap or len(b_bits) < min_overlap:
        return False
    return len(a_bits & b_bits) / max(len(a_bits), len(b_bits)) >= 0.8