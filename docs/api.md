# API Reference (Generated from actual code)

All paths are prefixed with `/api/v1` (see `app.api.v1.router`). Authentication uses Bearer JWT in `Authorization` header for most endpoints; refresh may also use httpOnly cookie with `X-Requested-With` header.

## auth (`/auth`)

| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/auth/login` | Public | Login with email/password; sets httpOnly refresh cookie, returns access token + user |
| POST | `/auth/refresh` | Public | Exchange refresh token (body or cookie + CSRF header) for new access/refresh; rotates refresh (denylist old JTI) |
| GET | `/auth/me` | Authenticated (any) | Return current user profile/claims |
| POST | `/auth/logout` | Public | Revoke refresh token (if present) and clear cookie; access token not required |
| POST | `/auth/activate` | Public | Activate account with token, set new password; returns tokens |
| POST | `/auth/change-password` | Authenticated | Change password (requires current password) |

Schemas: `LoginRequest`, `RefreshRequest`, `AccessToken`, `TokenPair`, `WhoAmISchema`, `ActivateAccountRequest`, `ChangePasswordRequest`, `LogoutRequest`, `Message`.

## students (`/students`)

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/students/me` | Authenticated | Get current student's full profile |
| PATCH | `/students/me` | Authenticated (student) | Update student’s self-editable fields (non-institutional) |
| GET | `/students/me/skills` | Authenticated (student) | List student’s skills |
| PUT | `/students/me/skills` | Authenticated (student) | Replace student’s skills (bulk upsert) |

Schemas: `StudentDetail`, `StudentSelfUpdate`, `SkillRead`, `SkillUpsert`.

## drives (`/drives`)

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/drives` | Authenticated | List published/closed drives (paginated; institution-scoped) |
| GET | `/drives/{drive_id}` | Authenticated | Get drive details if published/closed |
| GET | `/drives/{drive_id}/eligibility` | Student | Check eligibility for the drive (returns verdict with reasons) |
| GET | `/drives/{drive_id}/rounds` | Authenticated (student-visible) | List recruitment rounds for drive (order by position) — planned in Package B |

Schemas: `DriveRead`, `PaginatedDrives`, `DriveEligibilityCheck`, `EligibilityRuleOut`.

## resumes (`/resumes`)

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/resumes` | Authenticated (student) | List student’s resumes (includes extracted text/skills/parse status) |
| POST | `/resumes` | Authenticated (student) | Upload resume (multipart file); validates size/ext/mime, extracts text, detects skills |
| POST | `/resumes/analyze` | Authenticated (student) | Analyze resume against drive (drive_id required); returns skill match, gaps, feedback |
| POST | `/resumes/{resume_id}/set-primary` | Authenticated (student) | Set resume as primary |
| DELETE | `/resumes/{resume_id}` | Authenticated (student) | Delete resume (reassigns primary if deleted was primary) |
| POST | `/resumes/{drive_id}/roadmap` | Authenticated (student) | Generate preparation roadmap for drive; returns priority skills, steps, practice, skill gaps, disclaimer (includes `rounds` in Package B) |

Schemas: `ResumeDetail`, `ResumeUploadResponse`, `ResumeMetadata`, `ResumeAnalysisResult`, `PreparationRoadmap`.

## applications (`/applications`)

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/applications/me` | Authenticated (student) | List student’s own applications |
| POST | `/applications` | Authenticated (student) | Apply to published drive (resume_id optional); server re-evaluates eligibility, stores snapshot, creates history/notification |
| GET | `/applications/{application_id}` | Authenticated | View application (students see own only; admins see any in institution) |
| POST | `/applications/{application_id}/withdraw` | Authenticated (student) | Withdraw application (student-initiated); updates status and history |
| PATCH | `/applications/{application_id}/status` | Admin (UPDATE_APPLICATION_STATUS) | Update application status (forward-only; appends history) |
| GET | `/applications/drive/{drive_id}` | Admin (READ_ALL_APPLICATIONS) | List applications for a drive (institution-scoped) |

Schemas: `ApplicationRead`, `ApplicationDetail`, `ApplicationCreate`, `ApplicationStatusUpdate`, `WithdrawApplicationRequest`, `StatusHistoryRow`, `PaginatedApplications`.

## notifications (`/notifications`)

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/notifications` | Authenticated | List notifications for user (paginated, `unread_only` query). Package C: also triggers `ensure_deadline_reminders` lazily |
| POST | `/notifications/mark-read` | Authenticated | Mark notifications read (by ids or all unread) |

Schemas: `NotificationRead`, `PaginatedNotifications`, `NotificationMarkRead`.

## admin (`/admin`)

### students
| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/admin/students/import` | Admin (IMPORT_STUDENTS) | Bulk import students (max `max_import_rows`); returns created/skipped/failed and activation tokens if generated |
| GET | `/admin/students` | Admin (READ_ANY_STUDENT) | List students (paginate, filter by department/batch/q) |
| GET | `/admin/students/{student_id}` | Admin (READ_ANY_STUDENT) | Get student brief |
| PATCH | `/admin/students/{student_id}` | Admin (UPDATE_INSTITUTIONAL_STUDENT_FIELDS) | Update institutional (authoritative) student fields |

### companies
| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/admin/companies` | Admin (MANAGE_COMPANIES) | List companies (paginated) |
| POST | `/admin/companies` | Admin (MANAGE_COMPANIES) | Create company |
| PATCH | `/admin/companies/{company_id}` | Admin (MANAGE_COMPANIES) | Update company |

### drives
| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/admin/drives` | Admin (MANAGE_DRIVES) | List all drives in institution (with status/counts) |
| POST | `/admin/drives` | Admin (MANAGE_DRIVES) | Create drive |
| PATCH | `/admin/drives/{drive_id}` | Admin (MANAGE_DRIVES) | Update drive (fields + optional criteria/required_skills) |
| POST | `/admin/drives/{drive_id}/publish` | Admin (PUBLISH_DRIVE) | Publish drive (criteria may be provided/confirmed) |
| POST | `/admin/drives/{drive_id}/jd` | Admin (UPLOAD_JD) | Upload JD (multipart); extracts/suggests criteria/skills, sets AI extraction pending |
| POST | `/admin/drives/{drive_id}/jd/confirm` | Admin (CONFIRM_AI_EXTRACTION) | Confirm JD extraction (criteria + required_skills); marks eligibility confirmed |
| POST | `/admin/drives/{drive_id}/eligibility/evaluate` | Admin (MANAGE_ELIGIBILITY_CRITERIA) | Bulk evaluate eligibility for all students against drive |
| PUT | `/admin/drives/{drive_id}/rounds` | Admin (MANAGE_DRIVES or appropriate) | Replace drive rounds list (admin only, tenant-scoped, audit logged) — Package B |

### applications
| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/admin/applications` | Admin (READ_ALL_APPLICATIONS) | List all applications (filter by drive_id/status/department, paginated) |
| PATCH | `/admin/applications/{application_id}/status` | Admin (UPDATE_APPLICATION_STATUS) | Admin status update (forward-only, audit/history) |

### analytics & audit
| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/admin/analytics/summary` | Admin (READ_ANALYTICS) | Get analytics summary |
| GET | `/admin/analytics/funnel` | Admin (READ_ANALYTICS) | Get overall funnel |
| GET | `/admin/audit-log` | Admin (READ_AUDIT_LOG) | List audit log entries (paginate, filter by action/actor) |

### students/me (dashboard)
| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/students/me/dashboard` | Authenticated (student) | Return dashboard summary: eligible_open_drives (top 5 by nearest apply_by, days_left), closing_soon (within 72h), application_counts_by_status, top_skill_gaps — Package C |

## Notes
- Pagination: `page` and `limit` via `Pagination` dependency (defaults per config; max caps apply). Responses include `total`, `page`, `limit`, and for notifications also `unread_count`.
- Tenant isolation: all institution-scoped queries filter by `current.institution_id`; NotFound vs Permission errors used to avoid leaking existence.
- AI outputs: advisory only; failures degrade to deterministic fallbacks. AI analyses persisted with confirmation metadata where institutional decisions depend on them.
- Rate limiting: applied to auth/write/upload/AI routes as configured.
