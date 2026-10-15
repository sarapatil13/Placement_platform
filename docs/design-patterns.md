# Design Patterns

## AI Provider Strategy (Strategy + Result Object)

`app.services.ai_service` defines:
- `AIError`, `AIUnavailableError`, `AIValidationError` base classes
- Provider interface via function-based implementations (`_openai_compatible`, `_anthropic`, `_heuristic`) selected by `_provider_for()` based on `settings.ai_provider` and availability
- Result wrapper `AIResult[T]` carries `provider`, `model`, `value`, `raw_response`, `latency_ms`, `tokens_used`
- Pydantic schemas for typed outputs (`SkillComparisonSchema`, `PreparationRoadmapSchema`, `JDSuggestionSchema`)
- Public methods: `compare_skills`, `build_roadmap`, `suggest_jd_criteria` (all return `AIResult[...]` or raise `AIError`)

Pattern: Strategy (provider selection) + Value Object (AIResult) + Schema validation. Fallback to heuristic on errors (callers catch `AIError` and return deterministic results).

## Layered Architecture

Layers (top to bottom):
- API (`app.api.v1.*`): FastAPI routers, request/response validation via Pydantic schemas, auth/deps, rate limiting, audit context capture. No business logic beyond request orchestration and HTTP concerns.
- Services (`app.services.*`): Business logic (eligibility, applications, drives, resumes, students, tokens, notifications, analytics, audit). All institution-scoped and tenant-aware. Services use DB session and raise domain errors (`app.core.errors`).
- ORM/DB (`app.db.*`): SQLAlchemy models with `institution_id` on scoped entities, relationships, constraints, `Base`/mixins (`id_column`, timestamps). Alembic migrations.
- Core (`app.core.*`): Configuration (`config`, Pydantic settings), security (JWT, hashing, tokens, password policy), RBAC, errors, logging (`structlog`), crypto (field-level encryption helpers), rate limiting.

Dependency rule: API depends on Services + Schemas + Core; Services depend on Models/DB/Core; DB/Core have no upward deps.

## Application Status State Machine

States: `applied`, `in_review`, `shortlisted`, `interview`, `offered`, `rejected`, `withdrawn`, `offer_accepted`, `offer_declined`.
Transitions (`app.db.models.APP_TRANSITIONS`) are forward-only where applicable; terminal states `{rejected, withdrawn, offer_accepted, offer_declined}` have no outgoing transitions. 
Enforcement: `app.services.applications.ApplicationService.change_status()` validates transitions against `APP_TRANSITIONS` and `is_terminal()`. Every transition appends an `ApplicationStatusHistory` row (append-only). Withdrawal is student-initiated (`is_student_initiated=True`). Eligibility snapshot stored at application creation.

## Eligibility & Resume Snapshot

- Eligibility evaluation (`app.services.eligibility.evaluate`) checks confirmed criteria on `PlacementDrive.criteria` (active only), considers academic verification, missing CGPA → inconclusive. Returns `Verdict` with eligible flag, score, reasons, failed/passed rules, evaluated_at.
- Application creation stores `eligibility_snapshot` (deterministic outcome at apply time) so later rule changes don't retroactively alter the record.
- Resume snapshot: when applying with a resume, `resume_snapshot_text` is stored (frozen copy of extracted text sent with application). Primary resume concept tracked on `Resume`.

## Append-only History & Audit

- `ApplicationStatusHistory`: immutable timeline of status changes (from/to, changed_by/role, note, student-initiated). Ordered by `created_at`.
- `AuditLog`: append-only record of privileged actions/state changes (actor, action, entity, outcome, IP, user agent, detail, institution-scoped where applicable). Never updated/deleted by app code.
- `AIAnalysis`: persisted AI outputs with provider/model/schema, validated result, raw_response (debug-only), confirmation fields (`requires_confirmation`, `confirmed_by`, `confirmed_at`) for JD extraction/criteria confirmation paths.
- `RevokedRefreshToken` (denylist): keyed by JTI hash, expires_at indexed; pruned opportunistically (rotation on refresh).

## Selection Criteria for Patterns

- Strategy: provider abstraction with pluggable backends + uniform error handling/fallbacks (resilient, testable via mocks)
- Layered: clear separation of concerns, testability, RBAC/tenant checks localized
- State machine: explicit allowed transitions prevent invalid status jumps; auditability via history
- Snapshotting: immutability of decision context (eligibility at apply, resume text snapshot)
- Append-only audit: non-repudiation and forensic traceability
- Deterministic-by-default: AI is advisory with deterministic fallbacks (operational safety)
- Tenant isolation by design: `institution_id` on scoped models + filter-everywhere via deps/context
- Schema validation: Pydantic (I/O) + AI schema validation prevent untyped blobs entering system
