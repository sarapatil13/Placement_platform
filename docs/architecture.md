# Architecture

## Block Diagram (High-level)

```text
User (Browser)
  │
  ▼
Frontend (Vite/React/TS) — components/pages/lib/api
  │ HTTP (REST, JSON) + Vite proxy /api → :8000
  ▼
FastAPI (app.main) — CORS, rate limiting, lifespan, error handlers
  │
  ▼
API Routers (v1): auth, students, drives, resumes, applications, notifications, admin
  │
  ▼
Services (layer): users, students, drives, eligibility, resumes, applications, documents, skill_matching, ai_service, tokens, notifications, analytics, audit
  │
  ▼
DB/ORM: SQLAlchemy models + Alembic migrations (SQLite dev / PostgreSQL prod)
  │
  ▼
Storage: uploads under UPLOAD_DIR/<institution>/<student>/<sha256+ext>
  │
  ▼
AI Providers: heuristic (default, offline) | openai_compatible | anthropic (advisory; deterministic fallback on errors)
  │
  ▼
Core: config/settings, RBAC, security (JWT/crypto), logging (structlog), errors, rate limiting
```

## Key Components

- **Multi-tenancy**: Every scoped model has `institution_id` (FK to institutions). All queries filter by institution context from auth (`CurrentUser.institution_id`).
- **AuthN/Z**: JWT access/refresh with rotation + server-side denylist (JTI). httpOnly refresh cookie (SameSite=Strict), CSRF header for cookie-based refresh. RBAC via `Permission` enum per route.
- **Deterministic-first**: Eligibility evaluation is pure code. AI calls are advisory; all AI failures degrade to deterministic fallbacks.
- **Append-only history**: Application status history and audit log are never updated/deleted.
- **Tenant-scoped storage**: Resume/JD files stored under institution/student hierarchy with content-addressed names (sha256 prefix) and extension whitelists.

## Class Diagram (Models, high-level)

```text
Institution (1) ──< Department (N)
              ──< User (N)
              ──< Company (N)
              ──< PlacementDrive (N) ──< EligibilityCriterion (N)
                                     ──< DriveSkill (N)
                                     ──< Application (N)
User (1) ──o Student (1)
Student (1) ──< StudentSkill (N) >── Skill (N)
           ──< Resume (N)
           ──< Application (N)
Skill (1) ──< DriveSkill (N)
Company (1) ──< PlacementDrive (N)
Application (1) ──< ApplicationStatusHistory (N)
User (1) ──< Notification (N)  (user_id)
AIAnalysis: links to student/drive/resume/application (optional FKs)
AuditLog: institution/actor optional
RevokedRefreshToken: user_id + jti_hash (unique)
```

## ER Diagram (Core Entities)

```text
Institution (id, code unique) 1──N Department
1──N User
1──N Company
1──N PlacementDrive (company_id, institution_id)
1──N AuditLog

User 1──1 Student (user_id)
Student 1──N Resume
Student M──N Skill via StudentSkill
PlacementDrive M──N Skill via DriveSkill
PlacementDrive 1──N Application
Application 1──N ApplicationStatusHistory
User 1──N Notification
```

Crow's foot notation implied (1:N, M:N via junction tables StudentSkill/DriveSkill).

## Sequence Diagram 1: Student applies to a drive

```text
Student (Browser) -> API /applications (POST): drive_id, resume_id?, cover_note?
API -> deps: get_current_user (JWT), get_student_record
API -> ApplicationService.create(student, drive_id, resume_id, cover_note, resume_snapshot_text)
ApplicationService -> DB: load drive (published), check duplicate, check deadline
ApplicationService -> eligibility.evaluate_for_admission(drive_id, student)
eligibility: evaluate criteria against student (CGPA/backlogs/depts/batch/skills/...)
eligibility -> return Verdict (eligible/definitive/reasons)
ApplicationService -> DB: create Application (status=applied, eligibility_snapshot)
ApplicationService -> DB: create ApplicationStatusHistory (from=null -> applied, student_initiated=true)
ApplicationService -> notifications.create (application submitted)
ApplicationService -> commit -> return Application
API -> return ApplicationRead
```

Notes: eligibility is re-evaluated server-side at creation (client cannot self-declare). Snapshot stored at apply time.

## Sequence Diagram 2: Admin uploads JD -> confirms criteria -> publishes

```text
Admin (Browser) -> API /admin/drives/{drive_id}/jd (POST, multipart file)
API -> deps: require_permission(UPLOAD_JD), enforce content length
API -> drive_service.upload_jd_and_suggest(drive, filename, data, storage)
drive_service -> documents.extract_text_from_bytes(data, filename)
drive_service -> ai_service.suggest_jd_criteria(extracted_text, drive.title)
ai_service: try provider; on error -> fallback heuristic JD extraction
ai_service -> return JDSuggestionSchema (required_skills, suggested_min_cgpa, etc.)
drive_service -> DB: persist JD (jd_text, jd_filename, storage path), set is_ai_extraction_pending=true
drive_service -> persist AIAnalysis (requires_confirmation=true) if AI used
API -> return {drive_id, filename, ...suggestion}

Admin -> API /admin/drives/{drive_id}/jd/confirm (POST): criteria[], required_skills[]
API -> deps: require_permission(CONFIRM_AI_EXTRACTION)
API -> drive_service.confirm_extraction(drive, criteria, required_skills)
drive_service -> validate criteria
drive_service -> DB: upsert EligibilityCriterion rows (source ai_suggested_confirmed or admin_manual), set eligibility_confirmed=true/confirmed_by/at, clear pending flag
drive_service -> audit/log record
API -> return {confirmed: true}

Admin -> API /admin/drives/{drive_id}/publish (POST): criteria? (optional override)
API -> deps: require_permission(PUBLISH_DRIVE)
API -> drive_service.publish_drive(drive, criteria?)
drive_service -> ensure eligibility_confirmed or criteria provided; set status=published, published_at
drive_service -> DB: update drive, create notifications if applicable (out of scope here)
API -> return {status: published}
```

Notes: AI suggestions require explicit confirmation before publication (eligibility_confirmed is only set on confirm). Deterministic fallback applies if AI provider unavailable.

## Use-Case Diagram (core actors)

```text
Actors: Student, PlacementAdmin (placement cell), System (scheduler/automations)

Use cases:
Student: login/change password, view/update own profile/skills, list/view drives, check eligibility, upload/manage resumes, analyze resume vs drive, get prep roadmap, apply to drive, view/withdraw applications, view/mark notifications
PlacementAdmin: import students, manage students (institutional fields), manage companies, create/update drives, upload JD, confirm extraction, publish drive, manage criteria, evaluate eligibility (bulk), view/manage applications (update status), view analytics, view audit log
System: enforce RBAC/rate limits, JWT rotation/denylist, audit logging, storage validation, deterministic eligibility, AI fallback
```
