"""Deterministic, code-only skill matching.

Used for both resume-JD matching and JD-vs-student matching. AI may extract raw
skill strings, but the decision of matched / partial / missing is made here, in
plain code, so the platform never depends on an LLM for a machine decision.

Matching has three tiers, applied per required skill:
1. exact — the normalised strings are equal;
2. superset — every token of the required skill appears as a whole token of a
   listed skill (``react`` is matched by ``react native``);
3. partial — the token lists align and each token is a near-spelling
   (``javascript`` vs ``javascript es6`` is exact-ish, ``structures`` vs
   ``structure`` is partial).

Whole-token comparison is deliberate: it stops ``java`` from being counted as a
match for ``javascript`` just because the characters overlap.
"""

from __future__ import annotations

from collections.abc import Iterable
from difflib import SequenceMatcher

# Canonical spellings for common aliases. Keys are already-cleaned strings (the
# output of the cleaning pass in `normalize`). Values are canonical and, being
# clean themselves, are idempotent under another `normalize` call.
_ALIASES: dict[str, str] = {
    "js": "javascript",
    "java script": "javascript",
    "ts": "typescript",
    "reactjs": "react",
    "react js": "react",
    "nodejs": "nodejs",
    "node js": "nodejs",
    "golang": "go",
    "postgres": "postgresql",
    "psql": "postgresql",
    "k8s": "kubernetes",
    "ml": "machine learning",
    "dl": "deep learning",
    "ai": "artificial intelligence",
    "ds": "data structures",
    "dsa": "data structures and algorithms",
    "oop": "object oriented programming",
    "oops": "object oriented programming",
    "os": "operating systems",
    "html5": "html",
    "css3": "css",
    "rest": "rest api",
    "restful": "rest api",
    "rest api": "rest api",
    "tf": "tensorflow",
    "torch": "pytorch",
    "sklearn": "scikit learn",
    "scikit learn": "scikit learn",
    "powerbi": "power bi",
    "excel": "microsoft excel",
    "ms excel": "microsoft excel",
}

_TOKEN_RATIO = 0.85


def normalize(skill: str) -> str:
    """Lowercase, strip punctuation noise, collapse whitespace, apply aliases."""
    cleaned = " ".join(
        skill.strip().lower().replace(".", "").replace("-", " ").split()
    )
    return _ALIASES.get(cleaned, cleaned)


def match_skills(
    resume_skills: Iterable[str], required: Iterable[str]
) -> tuple[set[str], set[str], set[str]]:
    """Return ``(matched, partial, missing)`` sets of normalised required skills."""
    have_norm = {normalize(s) for s in resume_skills if s and s.strip()}
    required_norm = {normalize(s) for s in required if s and s.strip()}

    matched: set[str] = set()
    partial: set[str] = set()
    missing: set[str] = set()

    for req in required_norm:
        if req in have_norm:
            matched.add(req)
            continue
        req_tokens = req.split()
        superset = False
        near = False
        for have in have_norm:
            have_tokens = have.split()
            if req in have_tokens or set(req_tokens) <= set(have_tokens):
                superset = True
                break
            if _aligned_close(req_tokens, have_tokens):
                near = True
        if superset:
            matched.add(req)
        elif near:
            partial.add(req)
        else:
            missing.add(req)

    return matched, partial, missing


def _aligned_close(a_tokens: list[str], b_tokens: list[str]) -> bool:
    """True when two skills have the same number of tokens and each token pair is
    a near-spelling of the other (guards against partial-matching unrelated skills)."""
    if not a_tokens or len(a_tokens) != len(b_tokens):
        return False
    return all(_token_close(a, b) for a, b in zip(a_tokens, b_tokens, strict=True))


def _token_close(a: str, b: str) -> bool:
    if a == b:
        return True
    if len(a) < 4 or len(b) < 4:
        return False
    return SequenceMatcher(None, a, b).ratio() >= _TOKEN_RATIO
