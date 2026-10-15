"""Provider-agnostic AI service.

Guarantees:
- Every provider call returns a validated Pydantic model from a typed schema.
- Invalid, empty, or malformed LLM responses raise `AIValidationError` and are
  handled as a *failure* (fallible, logged, deterministic fallback) — never a crash.
- Eligibility is never decided by AI. AIAnalysis rows record only advisory data.

Providers:
- "heuristic" (default): deterministic local extractor. No network, works offline.
- "openai_compatible", "anthropic": external LLM via HTTP using structured-output
  prompting. Swappable for a local model by pointing ``AI_BASE_URL`` at it.
"""

from __future__ import annotations

import json
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("ai")

T = TypeVar("T", bound=BaseModel)


class AIError(Exception):
    """Any failure in the AI pipeline. Callers must degrade gracefully."""


class AIValidationError(AIError):
    """The LLM returned something that failed schema validation or was empty."""


class AIUnavailableError(AIError):
    """The provider is unreachable, misconfigured, or rate-limited."""


@dataclass
class AIResult(Generic[T]):
    value: T
    provider: str
    model: str
    latency_ms: int
    tokens_used: int | None = None
    raw_response: str | None = None


# --------------------------------------------------------------------------- #
# Schemas (typed, validated)
# --------------------------------------------------------------------------- #
class JDExtractionSchema(BaseModel):
    role_title: str | None = None
    location: str | None = None
    employment_type: str | None = None
    ctc_lpa: str | None = None
    stipend: str | None = None
    occupation_summary: str | None = None
    required_skills: list[str] = []
    preferred_skills: list[str] = []
    suggested_min_cgpa: float | None = None
    suggested_backlog_limit: int | None = None


class ResumeSkillExtractionSchema(BaseModel):
    skills: list[str] = []
    headline: str | None = None
    summary: str | None = None
    projects: list[str] = []


class SkillComparisonSchema(BaseModel):
    matched_skills: list[str] = []
    partial_skills: list[str] = []
    missing_skills: list[str] = []
    recommendations: list[str] = []


class PreparationRoadmapSchema(BaseModel):
    priority_skills: list[str] = []
    timeline_weeks: list[dict[str, Any]] = []
    suggested_resources: list[str] = []
    notes: str | None = None


# --------------------------------------------------------------------------- #
# Provider interface
# --------------------------------------------------------------------------- #
class AIService(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier stored in AIAnalysis.provider."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model identifier stored in AIAnalysis.model."""

    @abstractmethod
    def complete(self, schema: type[T], prompt: str, system: str | None = None) -> AIResult[T]:
        """Return a validated T or raise AIError."""


def _safe_load_json(content: str) -> dict[str, Any]:
    text = content.strip()
    # Tolerate ```json fenced blocks that some models add.
    if text.startswith("```"):
        text = "\n".join(
            line for line in text.splitlines() if not line.strip().startswith("```")
        ).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise AIValidationError(f"Provider returned invalid JSON: {exc}") from exc


class HeuristicAIService(AIService):
    """Deterministic, offline extractor. Counts as the default provider so the
    application is fully functional without an API key and tests never hit the
    network."""

    name = "heuristic"
    model_name = "deterministic-extractor-v1"

    # Surface forms of common technical skills. Matching is whole-token (see
    # `_find_skills`), so short ambiguous strings like bare "go"/"r" are omitted
    # and "java" never matches inside "javascript".
    _COMMON_SKILLS: tuple[str, ...] = (
        "python",
        "java",
        "javascript",
        "typescript",
        "c",
        "c++",
        "cpp",
        "c#",
        ".net",
        "golang",
        "rust",
        "php",
        "ruby",
        "kotlin",
        "swift",
        "scala",
        "dart",
        "react",
        "react native",
        "next.js",
        "vue",
        "angular",
        "node.js",
        "nodejs",
        "express",
        "django",
        "flask",
        "fastapi",
        "spring",
        "spring boot",
        "laravel",
        "rails",
        "hibernate",
        "redux",
        "jquery",
        "tailwind",
        "bootstrap",
        "sass",
        "html",
        "css",
        "graphql",
        "rest",
        "rest api",
        "microservices",
        "sql",
        "mysql",
        "postgresql",
        "sqlite",
        "mongodb",
        "redis",
        "kafka",
        "spark",
        "hadoop",
        "airflow",
        "elasticsearch",
        "git",
        "github",
        "gitlab",
        "bitbucket",
        "docker",
        "kubernetes",
        "terraform",
        "ansible",
        "jenkins",
        "ci cd",
        "linux",
        "bash",
        "shell",
        "aws",
        "gcp",
        "azure",
        "machine learning",
        "deep learning",
        "artificial intelligence",
        "nlp",
        "computer vision",
        "tensorflow",
        "pytorch",
        "keras",
        "scikit learn",
        "pandas",
        "numpy",
        "matplotlib",
        "seaborn",
        "statistics",
        "power bi",
        "tableau",
        "microsoft excel",
        "data structures",
        "algorithms",
        "dbms",
        "computer networks",
        "operating systems",
        "oops",
        "object oriented programming",
        "system design",
        "cypress",
        "jest",
        "pytest",
        "selenium",
        "postman",
        "figma",
        "android",
        "ios",
        "flutter",
    )

    def _find_skills(self, lowered_text: str) -> list[str]:
        """Return the known skills present as whole tokens in ``lowered_text``."""
        found: list[str] = []
        for skill in self._COMMON_SKILLS:
            pattern = r"(?<![a-z0-9])" + re.escape(skill) + r"(?![a-z0-9])"
            if re.search(pattern, lowered_text):
                found.append(skill)
        return found

    def complete(self, schema: type[T], prompt: str, system: str | None = None) -> AIResult[T]:
        from typing import cast

        start = time.perf_counter()
        try:
            parsed: JDExtractionSchema | (
                ResumeSkillExtractionSchema | SkillComparisonSchema | PreparationRoadmapSchema
            )
            if schema is JDExtractionSchema:
                parsed = self._extract_jd(prompt)
            elif schema is ResumeSkillExtractionSchema:
                parsed = self._extract_resume_skills(prompt)
            elif schema is SkillComparisonSchema:
                parsed = self._compare_skills(prompt)
            elif schema is PreparationRoadmapSchema:
                parsed = self._roadmap(prompt)
            else:
                raise AIValidationError(f"Unsupported schema for heuristic provider: {schema}")
            latency = int((time.perf_counter() - start) * 1000)
            return AIResult(
                value=cast(T, parsed), provider=self.name, model=self.model_name, latency_ms=latency
            )
        except AIError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            raise AIValidationError(f"Heuristic provider failed: {exc}") from exc

    # -- implementations ---------------------------------------------------- #
    def _extract_jd(self, prompt: str) -> JDExtractionSchema:
        text = self._last_user_text(prompt)
        lowered = text.lower()
        skills = self._find_skills(lowered)
        # crude CGPA/backlog hints only; these are *suggestions* the admin confirms.
        cgpa = None
        for token in ("cgpa", "aggregate"):
            idx = lowered.find(token)
            if idx != -1:
                for word in lowered[idx : idx + 40].split():
                    try:
                        candidate = float(word.rstrip(",.;%)"))
                        if 0 <= candidate <= 10:
                            cgpa = candidate
                            break
                    except ValueError:
                        continue
                if cgpa is not None:
                    break
        role = None
        if "software engineer" in lowered:
            role = "Software Engineer"
        elif "developer" in lowered:
            role = "Developer"
        if role is None:
            for line in text.splitlines():
                if line and "intern" in line.lower():
                    role = line.strip()[:90]
                    break
        return JDExtractionSchema(
            role_title=role,
            required_skills=skills[:12],
            suggested_min_cgpa=cgpa,
        )

    def _extract_resume_skills(self, prompt: str) -> ResumeSkillExtractionSchema:
        text = self._last_user_text(prompt).lower()
        skills = self._find_skills(text)
        return ResumeSkillExtractionSchema(skills=skills[:30])

    def _compare_skills(self, prompt: str) -> SkillComparisonSchema:
        # Deterministic fallback: recompute from the prompt, which embeds the
        # resume skills and required skills in JSON. If they are present, mirror
        # the server-side matcher so the stored analysis is internally consistent.
        m_resume = re.search(r'"resume_skills"\s*:\s*(\[[^\]]*\])', prompt)
        m_required = re.search(r'"required_skills"\s*:\s*(\[[^\]]*\])', prompt)
        if m_resume and m_required:
            try:
                resume_skills = json.loads(m_resume.group(1))
                required = json.loads(m_required.group(1))
                return self._match(resume_skills, required)
            except json.JSONDecodeError:
                pass
        return SkillComparisonSchema()

    def _match(
        self, resume_skills: list[str], required: list[str]
    ) -> SkillComparisonSchema:
        from app.services.skill_matching import match_skills

        matched, partial, missing = match_skills(set(resume_skills), set(required))
        return SkillComparisonSchema(
            matched_skills=sorted(matched),
            partial_skills=sorted(partial),
            missing_skills=sorted(missing),
            recommendations=[
                f"Strong weight on {', '.join(sorted(missing)[:4])}" if missing else "No immediate gaps."
            ],
        )

    def _roadmap(self, prompt: str) -> PreparationRoadmapSchema:
        m_missing = re.search(r'"missing_skills"\s*:\s*(\[[^\]]*\])', prompt)
        missing: list[str] = []
        if m_missing:
            try:
                missing = json.loads(m_missing.group(1))
            except json.JSONDecodeError:
                missing = []
        return PreparationRoadmapSchema(
            priority_skills=sorted(missing),
            timeline_weeks=[
                {"week": i + 1, "skills": group}
                for i, group in enumerate(self._chunks(sorted(missing), 2))
            ],
            suggested_resources=[
                f"LeetCode topic track: {s}" for s in sorted(missing)[:4]
            ],
            notes="Generated from the verified skill-gap analysis.",
        )

    @staticmethod
    def _chunks(items: list[str], n: int) -> list[list[str]]:
        return [items[i : i + n] for i in range(0, len(items), n)]

    @staticmethod
    def _last_user_text(prompt: str) -> str:
        # The heuristic provider receives the raw text as the body after "RESUME_OR_JD_TEXT".
        marker = "RESUME_OR_JD_TEXT"
        idx = prompt.find(marker)
        return prompt[idx + len(marker) :].strip() if idx != -1 else prompt


class OpenAICompatibleAIService(AIService):
    """Call any /chat/completions endpoint with JSON-mode guidance.

    Point ``AI_BASE_URL`` at a local model (e.g. vLLM/llama.cpp) to swap the LLM
    without touching business logic.
    """

    name = "openai_compatible"
    model_name = settings.ai_model or "gpt-4o-mini"

    def complete(self, schema: type[T], prompt: str, system: str | None = None) -> AIResult[T]:
        if not settings.ai_api_key and settings.environment != "development":
            raise AIUnavailableError("AI_API_KEY is not configured.")

        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": system
                    or (
                        "You extract structured data from job descriptions and resumes. "
                        "Respond with a single valid JSON object matching the requested schema. "
                        "Never estimate or invent fields: return null for unknown details."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        headers = {"Content-Type": "application/json"}
        if settings.ai_api_key:
            headers["Authorization"] = f"Bearer {settings.ai_api_key}"

        start = time.perf_counter()
        try:
            resp = httpx.post(
                f"{settings.ai_base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
                timeout=settings.ai_timeout_seconds,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as exc:
            raise AIUnavailableError(f"LLM HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, KeyError, IndexError, TypeError) as exc:
            raise AIUnavailableError(f"LLM request failed: {exc}") from exc
        finally:
            latency = int((time.perf_counter() - start) * 1000)

        data = _safe_load_json(str(content))
        try:
            value = schema.model_validate(data)
        except ValidationError as exc:
            raise AIValidationError(f"LLM response failed validation: {exc}") from exc
        return AIResult(
            value=value,
            provider=self.name,
            model=self.model_name,
            latency_ms=latency,
            raw_response=str(content),
        )


class AnthropicAIService(AIService):
    name = "anthropic"
    model_name = settings.ai_model or "claude-sonnet-4-5"

    def complete(self, schema: type[T], prompt: str, system: str | None = None) -> AIResult[T]:
        if not settings.ai_api_key and settings.environment != "development":
            raise AIUnavailableError("AI_API_KEY is not configured.")

        payload = {
            "model": self.model_name,
            "system": system or "You extract structured JSON only.",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1200,
            "temperature": 0,
        }
        headers = {"Content-Type": "application/json", "x-api-key": settings.ai_api_key}
        start = time.perf_counter()
        try:
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                json=payload,
                headers=headers,
                timeout=settings.ai_timeout_seconds,
            )
            resp.raise_for_status()
            content = resp.json()["content"][0]["text"]
        except httpx.HTTPStatusError as exc:
            raise AIUnavailableError(f"Anthropic HTTP {exc.response.status_code}") from exc
        except (httpx.HTTPError, KeyError, IndexError, TypeError) as exc:
            raise AIUnavailableError(f"Anthropic request failed: {exc}") from exc
        finally:
            latency = int((time.perf_counter() - start) * 1000)

        data = _safe_load_json(str(content))
        try:
            value = schema.model_validate(data)
        except ValidationError as exc:
            raise AIValidationError(f"Anthropic response failed validation: {exc}") from exc
        return AIResult(
            value=value, provider=self.name, model=self.model_name, latency_ms=latency
        )


_providers: dict[str, type[AIService]] = {
    "heuristic": HeuristicAIService,
    "openai_compatible": OpenAICompatibleAIService,
    "anthropic": AnthropicAIService,
    "local": HeuristicAIService,  # local == deterministic until a model is configured
}


def get_ai_service() -> AIService:
    """Return the configured provider. Unknown/none falls back to heuristic."""
    configured = settings.ai_provider
    if not settings.ai_enabled or configured not in _providers:
        logger.warning("ai.provider_fallback", configured=configured)
        return HeuristicAIService()
    return _providers[configured]()


def extract_jd_fields(text: str) -> AIResult[JDExtractionSchema]:
    prompt = (
        "Extract the following from this job description. Return JSON matching the schema.\n"
        "RESUME_OR_JD_TEXT\n" + text
    )
    return get_ai_service().complete(JDExtractionSchema, prompt)


def extract_resume_skills(text: str) -> AIResult[ResumeSkillExtractionSchema]:
    prompt = (
        "Extract a list of technical skills from this resume. Return JSON matching the schema.\n"
        "RESUME_OR_JD_TEXT\n" + text[:8000]
    )
    return get_ai_service().complete(ResumeSkillExtractionSchema, prompt)


def compare_skills(
    resume_skills: list[str], required_skills: list[str]
) -> AIResult[SkillComparisonSchema]:
    prompt = json.dumps(
        {"resume_skills": sorted(resume_skills), "required_skills": sorted(required_skills)},
        ensure_ascii=False,
    )
    return get_ai_service().complete(SkillComparisonSchema, prompt)


def build_roadmap(
    missing_skills: list[str], matched_skills: list[str], drive_title: str
) -> AIResult[PreparationRoadmapSchema]:
    prompt = json.dumps(
        {
            "drive": drive_title,
            "missing_skills": sorted(missing_skills),
            "matched_skills": sorted(matched_skills),
        },
        ensure_ascii=False,
    )
    return get_ai_service().complete(PreparationRoadmapSchema, prompt)