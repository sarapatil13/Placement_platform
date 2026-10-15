# Architecture

## Block Diagram (High-level)

```mermaid
flowchart TD
    U[User / Browser]
    FE["Frontend (Vite + React + TS)<br/>pages / components / lib / api"]
    API["FastAPI app.main<br/>CORS, rate limiting, lifespan, error handlers"]
    ROUTERS["API Routers v1<br/>auth · students · drives · resumes · applications · notifications · admin"]
    SERVICES["Service layer<br/>users · students · drives · eligibility · resumes · applications<br/>documents · skill_matching · ai_service · tokens · notifications · analytics · audit"]
    DB["DB / ORM<br/>SQLAlchemy models + Alembic migrations<br/>SQLite dev / PostgreSQL prod"]
    STORE["Storage<br/>UPLOAD_DIR/&lt;institution&gt;/&lt;student&gt;/&lt;sha256+ext&gt;"]
    AI["AI Providers<br/>heuristic (default, offline) · openai_compatible · anthropic<br/>advisory only; deterministic fallback on errors"]
    CORE["Core<br/>config · RBAC · security (JWT/crypto) · logging · errors · rate limiting"]

    U --> FE
    FE -->|"REST / JSON · Vite proxy /api → :8000"| API
    API --> ROUTERS
    ROUTERS --> SERVICES
    SERVICES --> DB
    SERVICES --> STORE
    SERVICES --> AI
    ROUTERS -.->|uses| AI
    DB --- CORE
    SERVICES --- AI
    API --> AI
```

## Key Components

- **Multi-tenancy**: Every scoped model has `institution_id` (FK to institutions). All queries filter by institution context from auth (`CurrentUser.institution_id`).
- **AuthN/Z**: JWT access/refresh with rotation + server-side denylist (JTI). httpOnly refresh cookie (SameSite=Strict), CSRF header for cookie-based refresh. RBAC via `Permission` enum per route.
- **Deterministic-first**: Eligibility evaluation is pure code. AI calls are advisory; all AI failures degrade to deterministic fallbacks.
- **Append-only history**: Application status history and audit log are never updated/deleted.
- **Tenant-scoped storage**: Resume/JD files stored under an institution/student hierarchy with content-addressed names (sha256 prefix) and extension whitelists.
- **Interview rounds**: A drive owns an ordered list of `DriveRound` rows (online assessment, technical/HR interviews, group discussion, other), editable by admins and read by students; prep-roadmap focus skills are derived from round topics.

## Class Diagram (Models, high-level)

```mermaid
classDiagram
    Institution "1" --> "N" Department
    Institution "1" --> "N" User
    Institution "1" --> "N" Company
    Institution "1" --> "N" PlacementDrive
    Company "1" --> "N" PlacementDrive
    PlacementDrive "1" --> "N" EligibilityCriterion
    PlacementDrive "1" --> "N" DriveSkill
    PlacementDrive "1" --> "N" DriveRound
    PlacementDrive "1" --> "N" Application
    User "1" --o "1" Student
    Student "1" --> "N" StudentSkill
    Student "1" --> "N" Resume
    Student "1" --> "N" Application
    Skill "1" --> "N" StudentSkill
    Skill "1" --> "N" DriveSkill
    Application "1" --> "N" ApplicationStatusHistory
    User "1" --> "N" Notification
    User "1" --> "N" RevokedRefreshToken
```

`AIAnalysis` links optionally to student/drive/resume/application. `AuditLog` references an optional institution/actor.

## ER Diagram (Core Entities)

```mermaid
erDiagram
    INSTITUTION ||--o{ DEPARTMENT : has
    INSTITUTION ||--o{ USER : has
    INSTITUTION ||--o{ COMPANY : has
    INSTITUTION ||--o{ PLACEMENT_DRIVE : has
    INSTITUTION ||--o{ AUDIT_LOG : records
    USER ||--o| STUDENT : "is a"
    USER ||--o{ NOTIFICATION : receives
    USER ||--o{ REVOKED_REFRESH_TOKEN : revokes
    STUDENT ||--o{ RESUME : owns
    STUDENT }o--o{ SKILL : "via StudentSkill"
    PLACEMENT_DRIVE }o--o{ SKILL : "via DriveSkill"
    PLACEMENT_DRIVE ||--o{ DRIVE_ROUND : schedules
    PLACEMENT_DRIVE ||--o{ APPLICATION : receives
    APPLICATION ||--o{ APPLICATION_STATUS_HISTORY : logs

    INSTITUTION {
        string id PK
        string code UK
    }
    PLACEMENT_DRIVE {
        string id PK
        string company_id FK
        string institution_id FK
        string status
    }
    DRIVE_ROUND {
        string id PK
        string drive_id FK
        int position
        string round_type
        json topics
        datetime scheduled_at
    }
```

## Sequence Diagram 1: Student applies to a drive

```mermaid
sequenceDiagram
    participant S as Student (Browser)
    participant API as API /applications
    participant SVC as ApplicationService
    participant EL as eligibility.evaluate_for_admission
    participant DB as Database

    S->>API: POST drive_id, resume_id?, cover_note?
    API->>API: get_current_user (JWT) + get_student_record
    API->>SVC: create(student, drive_id, resume_id, cover_note, snapshot)
    SVC->>DB: load drive (published), check duplicate + deadline
    SVC->>EL: evaluate_for_admission(drive_id, student)
    EL->>EL: evaluate criteria (CGPA/backlogs/depts/batch/skills)
    EL-->>SVC: Verdict(eligible, definitive, reasons)
    SVC->>DB: insert Application(status=applied, eligibility_snapshot)
    SVC->>DB: insert ApplicationStatusHistory(null -> applied)
    SVC->>DB: notifications.create(application submitted)
    SVC->>DB: commit
    SVC-->>API: Application
    API-->>S: ApplicationRead
```

Notes: eligibility is re-evaluated server-side at creation (client cannot self-declare). Snapshot stored at apply time.

## Sequence Diagram 2: Admin uploads JD -> confirms criteria -> publishes

```mermaid
sequenceDiagram
    participant A as Admin (Browser)
    participant API as Admin API
    participant DS as drive_service
    participant AI as ai_service
    participant DB as Database

    A->>API: POST /admin/drives/{id}/jd (multipart)
    API->>API: require_permission(UPLOAD_JD) + enforce content length
    API->>DS: upload_jd_and_suggest(drive, filename, data, storage)
    DS->>DS: documents.extract_text_from_bytes(data, filename)
    DS->>AI: suggest_jd_criteria(text, title)
    AI-->>DS: JDSuggestionSchema (on error: heuristic fallback)
    DS->>DB: persist JD, set is_ai_extraction_pending=true
    DS->>DB: persist AIAnalysis(requires_confirmation=true)
    API-->>A: {drive_id, filename, ...suggestion}

    A->>API: POST /admin/drives/{id}/jd/confirm criteria[], required_skills[]
    API->>API: require_permission(CONFIRM_AI_EXTRACTION)
    API->>DS: confirm_extraction(drive, criteria, required_skills)
    DS->>DS: validate criteria
    DS->>DB: upsert EligibilityCriterion rows, set eligibility_confirmed
    DS->>DB: audit log
    API-->>A: {confirmed: true}

    A->>API: POST /admin/drives/{id}/publish criteria?
    API->>API: require_permission(PUBLISH_DRIVE)
    API->>DS: publish_drive(drive, criteria?)
    DS->>DB: set status=published, published_at
    DS->>DB: notifications to eligible students
    API-->>A: {status: published}
```

Notes: AI suggestions require explicit confirmation before publication (eligibility_confirmed is only set on confirm). Deterministic fallback applies if the AI provider is unavailable.

## Sequence Diagram 3: Admin maintains drive rounds

```mermaid
sequenceDiagram
    participant A as Admin (Browser)
    participant API as Admin API
    participant DS as drive_service
    participant DB as Database

    A->>API: PUT /admin/drives/{id}/rounds {rounds:[...]}
    API->>API: require_permission(MANAGE_DRIVES) + validate round types
    API->>DS: replace_rounds(drive, rounds)
    DS->>DS: reject duplicate positions
    DS->>DB: delete existing rounds, insert new rounds
    DS->>DB: audit log (drive.rounds_updated)
    API-->>A: {drive_id, rounds:[...]}
```

Students read the same list (ordered by `position`) via `GET /drives/{id}/rounds`, and the list feeds per-round `focus_skills` in the preparation roadmap.

## Use-Case Diagram (core actors)

```mermaid
flowchart LR
    subgraph Actors
        ST([Student])
        PA([Placement Admin])
        SY([System])
    end

    subgraph Student use cases
        S1[Login / change password]
        S2[Manage profile + skills]
        S3[Browse drives]
        S4[Check eligibility]
        S5[Manage resumes]
        S6[Analyze resume vs drive]
        S7[Prep roadmap]
        S8[Apply / withdraw]
        S9[Notifications]
    end

    subgraph Admin use cases
        A1[Import students]
        A2[Manage institutional data]
        A3[Manage companies]
        A4[Create / update drives]
        A5[Upload JD + confirm]
        A6[Manage rounds]
        A7[Publish drive]
        A8[Evaluate eligibility]
        A9[Manage applications]
        A10[Analytics + audit log]
    end

    subgraph System use cases
        Y1[Enforce RBAC / rate limits]
        Y2[JWT rotation / denylist]
        Y3[Audit logging]
        Y4[Storage validation]
        Y5[Deterministic eligibility]
        Y6[AI fallback]
    end

    ST --> S1 & S2 & S3 & S4 & S5 & S6 & S7 & S8 & S9
    PA --> A1 & A2 & A3 & A4 & A5 & A6 & A7 & A8 & A9 & A10
    SY --> Y1 & Y2 & Y3 & Y4 & Y5 & Y6
```
