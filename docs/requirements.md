# Requirements (SPNP)

This document derives functional and non-functional requirements from the current codebase (models, schemas, services, API routes, RBAC).

## Functional Requirements (FR)

FR1. **Multi-tenancy**: The system isolates data by `institution_id` across all scoped entities (users, students, departments, companies, drives, applications, notifications, analyses, audit logs). Cross-institution access is rejected.

FR2. **Authentication & authorization**: JWT-based auth with access/refresh tokens, refresh rotation and server-side denylist (JTI), httpOnly refresh cookie with SameSite=Strict and CSRF header protection. RBAC via `Permission` enum; role-permission matrix enforced on protected routes.

FR3. **Account lifecycle**: Admins can import/provision students (bulk import with limits, `max_import_rows`). Provisioned student accounts may require activation/password change (`must_change_password`). Self-registration respects `institution.allow_self_registration`.

FR4. **Student profile**: Students can read/update their own contact/profile fields; authoritative academic fields (college_id, department, batch_year, cgpa, backlog counts, academic verification flags) are institution-owned and only writable by authorized admin paths. Students manage their own skills (read/replace).

FR5. **Resumes**: Students upload resumes (PDF/DOCX, size/extension/mime validated, per-student cap). Text is extracted, skills detected (deterministic), parse status recorded. Students can list, set primary, delete, analyze against a drive, and generate a preparation roadmap.

FR6. **Companies**: Admins manage companies (CRUD) within institution. Drives reference companies; company name shown in drive views.

FR7. **Placement drives**: Admins create/update drives, upload JDs (extract/suggest criteria/skills), confirm AI extraction, publish drives (criteria confirmed), and evaluate eligibility in bulk. Students view published/closed drives, check eligibility, and apply.

FR8. **Eligibility**: Deterministic eligibility evaluation against confirmed criteria (CGPA min/max, backlog max, departments, batch years, skill match threshold, age/gender/percentile as defined). Eligibility snapshot is stored at application time.

FR9. **Applications**: Students may apply to published drives (with optional resume/cover note). Each student may apply once per drive. Application status follows a forward-only state machine with audit history. Students view their applications; admins view/manage applications by drive/status/department and update statuses.

FR10. **Notifications**: Users receive notifications (application submitted, status changes, etc.). Users list notifications (paginated), mark read; unread count included.

FR11. **Analytics & audit**: Admins access analytics summary/funnel and an append-only audit log (filterable by action/actor, institution-scoped). AI analyses are persisted (provider/model/schema/result, confirmation metadata).

FR12. **AI advisory**: Resume-JD matching and preparation roadmap use pluggable AI providers with deterministic fallbacks on error; AI outputs never override authoritative eligibility/academic data and require human confirmation where they inform institutional decisions.

## Non-Functional Requirements (NFR)

NFR1. **Privacy & tenant safety**: `institution_id` on all institution-scoped tables; all queries filter by institution context. Tenant isolation is enforced by dependencies and service layer usage.

NFR2. **Security**: JWT rotation + denylist, httpOnly SameSite=Strict cookies, CSRF header for cookie refresh, rate limiting on sensitive/auth/write/upload/AI endpoints, password policy, content-length enforcement on uploads, production guards (`ensure_production_safe`).

NFR3. **Determinism & safety**: Eligibility is deterministic. AI failures return deterministic fallbacks (no 5xx from provider errors). Critical state changes recorded in audit log and application status history (append-only).

NFR4. **Resiliency & validation**: Pydantic schemas validate I/O, upload validation (mime/ext/size), document extraction size/limits, bulk import capped (`max_import_rows`). AI responses validated against provider schemas.

NFR5. **Observability**: Structured logging (`structlog`), request IDs, audit trail for privileged actions. AI call metadata (latency/tokens/status) persisted.

NFR6. **Configurability**: Institution-specific settings via `.env`/Pydantic settings (branding, grading scale, backlog semantics, CORS, limits, AI provider). No hard-coded university-specific rules outside configuration where policy is involved.

NFR7. **Performance & paging**: List endpoints support pagination (`page`, `limit`) with caps. Large reads are paginated.

NFR8. **Portability**: SQLite default for dev, PostgreSQL enforced in production; filesystem paths configurable; storage under `UPLOAD_DIR`.

## Assumptions
- Reverse proxy may set `X-Forwarded-For`; trusted proxies must be explicitly configured via `TRUSTED_PROXY` (never trusted by default).
- File storage is local filesystem under configured upload dir; no cloud object storage in core paths.
- AI providers are optional; heuristic/fallback path must always function for core flows.
- Emails are not sent by the application (no email sending code paths present).
- Academic data changes require placement-cell permissions; students cannot modify authoritative fields.

## Constraints
- Python 3.11+, FastAPI/SQLAlchemy stack, no new dependencies to be added (per task).
- Keep changes minimal and consistent with existing code style.
- No mock interviews/quizzes/streaks, no email sending.
- Production rejects insecure defaults (sqlite in prod, missing Fernet key, weak/placeholder secret key, wildcard CORS, debug on, seed_on_startup true, rate limiting disabled).
