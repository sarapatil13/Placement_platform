# Algorithms (Pseudo-code with Inputs/Outputs)

All algorithms below reflect the current implementation. AI steps are advisory; classification and eligibility are deterministic.

## 1. Eligibility Evaluation

**Location:** `app.services.eligibility.evaluate(student, drive_id, criteria=None) -> Verdict`
- Inputs: `student` (ORM), `drive_id`, optional `criteria` list
- Output: `Verdict` {eligible, definitive (bool, if any rule inconclusive → definitive False), score, reasons[], failed_rules[], passed_rules[], evaluated_at}

Pseudo-code:
1. Load drive + active criteria (if `criteria` not provided, use `drive.criteria` where `is_active` True; order by creation)
2. `definitive = True`, `passed = []`, `failed = []`, `reasons = []`
3. For each criterion:
   - if type `cgpa_min`: require `student.cgpa` exists and academic_verified context; if missing → `inconclusive`, `definitive=False`, reason recorded; else check `student.cgpa >= threshold`
   - if type `cgpa_max`: symmetric; missing → inconclusive
   - if type `backlog_max`: check `active_backlogs`/`backlog_count` against limits; missing counts → inconclusive as appropriate per rule
   - if type `departments`: require `student.department.code` in allowed set
   - if type `batch_years`: require `student.batch_year` in allowed set
   - if type `skill_min_match`: compute match ratio (see #2) against drive required skills; require >= threshold (rule carries threshold in parameters)
   - if type `age_max`/`gender`/`percentile_min`: evaluated from student fields as present in parameters
4. Aggregate: `eligible = all decisive rules pass AND no rule decisively failed` (but if any inconclusive and others pass, `eligible` may be True only if decisive rules all pass? The implementation treats inconclusive as not a pass/fail that blocks when decisive rules pass; see code: verdict.eligible is True only if every rule is either passed or inconclusive in a way that doesn’t force fail? The code sets `eligible = len(results) > 0 and all(r.passed for r in results)` when all are decisive; if any inconclusive, the logic allows `definitive=False` while eligible may be False in practice depending on failed rules.)  
   (Implementation detail is reflected in code; see `evaluate` for exact logic.)

Notes: `evaluate_for_admission` wraps evaluate and returns the verdict used at application time.

## 2. Skill Matching (Deterministic)

**Location:** `app.services.skill_matching.match_skills(resume_skills, required) -> (matched, partial, missing)`
- Inputs: iterables of skill names
- Output: three sets (normalized forms returned as the matched/partial/missing skill strings as processed)

Normalization:
- `normalize(s) = s.strip().lower().replace('.', '').replace('-', ' ')`

Algorithm:
1. Build `resume_norm = {normalize(s) for s in resume_skills if s}`
2. Build `required_norm = {normalize(s) for s in required if s}`
3. For each `req` in `required_norm`:
   - if `req in resume_norm`: add `req` to `matched` (lowercased form as stored) — continue
   - else scan `resume_norm` for:
     - if `req in have and len(req) >= 4`: add `req` to `matched`; break (substring/superset match)
     - if `_closeness(req, have)` is True and `len(req) >= 5`: add `req` to `partial`; break  
       where `_closeness(a,b,min_overlap=4)`: let `A=set(a), B=set(b)`. If `|A|<min_overlap or |B|<min_overlap`: False. Else `|A∩B| / max(|A|,|B|) >= 0.8`
   - if found any → continue; else add `req` to `missing`
4. Return (matched, partial, missing)

**Planned change in Package D** (per task): replace `_closeness` heuristic with an alias map applied in `normalize()` (e.g., js/javascript, cpp/c++, ml/machine learning, node/nodejs/node.js, postgres/postgresql, k8s/kubernetes, cn/computer networks, os/operating systems, db/dbms, ds/data structures, dsa/data structures and algorithms, oop/oops/object oriented programming). Partial becomes “shares a whole word token with the required skill (min length 3)”, not character-set overlap. (Task states this explicitly.)

## 3. JD/Resume Extraction (Heuristic Fallback)

**Location:** `app.services.ai_service.HeuristicAIService`

- `_extract_jd(prompt)`: extracts from last user message text. Looks for keywords: common skills from `_COMMON_SKILLS`, crude CGPA hints (0-10), infers role from "software engineer"/"developer"/"intern" lines. Returns `JDExtractionSchema` with `role_title`, `required_skills[:12]`, `suggested_min_cgpa`.
- `_extract_resume_skills(prompt)`: scans text for `_COMMON_SKILLS`, returns `ResumeSkillExtractionSchema(skills[:30])`.
- Provider path (external): `OpenAICompatibleAIService.complete`/`AnthropicAIService.complete` call HTTP with JSON schema, parse fenced JSON, validate via Pydantic. On HTTP error/timeout/validation → `AIError` subclasses; callers degrade to deterministic fallback.
- `suggest_jd_criteria(text, drive_title)`: heuristic returns JDExtractionSchema; provider path similar.

Outputs: validated Pydantic models; raw response retained in AIResult for audit.

## 4. Application Status Change (Forward-only)

**Location:** `app.services.applications.ApplicationService.change_status(application_id, new_status, note=None)`

Inputs: `application_id`, `new_status`, optional `note`
Output: updated `Application` ORM object

Pseudo-code:
1. Load application; ensure institution matches (service uses DB session context; routes enforce scope)
2. If application.status is terminal (`not APP_TRANSITIONS[status]`): raise `ValidationError` ("cannot change status of a terminal application")
3. Allowed = `APP_TRANSITIONS[current_status]`
4. If `new_status` not in allowed: raise `ValidationError` ("Invalid status transition …")
5. Append `ApplicationStatusHistory`: from_status=current, to_status=new, changed_by/role from actor_ctx, note, is_student_initiated=False
6. Set `application.status = new_status`, touch updated_at
7. Record audit `application.status_changed`
8. Commit and refresh
9. Return application

Constraints: forward-only; terminal states never change; append-only history.

## 5. Deadline Reminders (Lazily Generated)

**Planned (Package C):** `app.services.notifications.ensure_deadline_reminders(db, user, student)`

Inputs: `db`, `user` (ORM), `student` (ORM)
Output: None (creates notifications as side effect)

Behavior (per task):
- Find published drives with `apply_by` within the next 48 hours (relative to current time, UTC) such that the student is eligible for them AND has not applied to them
- For each such (user, drive), create one `"deadline_soon"` notification if none exists with the same type + payload containing `drive_id` (idempotent check)
- Call lazily from `GET /notifications` and from new `GET /students/me/dashboard`

Idempotency: check existing notifications by `type="deadline_soon"` and `payload.drive_id == drive.id` for that user (and same institution). Create only if missing.

Eligibility check: reuse `evaluate`/admission eligibility logic for the student against that drive (or equivalent) — must reflect current confirmed criteria.

## 6. Round-wise Roadmap (Focus Skills per Round)

**Planned (Package B):** extend `build_prep_roadmap` to also return `rounds`.

Inputs/outputs (current roadmap dict): has `drive_id`, `priority_skills`, `roadmap_steps`, `suggested_practice`, `skill_gaps`, `disclaimer`. New key `rounds`.

For each `DriveRound` (ordered by `position`):
- `title`, `round_type`, `topics` (list of strings)
- `focus_skills`: intersection of student’s missing skills (from the roadmap’s missing set, i.e. skills required by drive but not present in student’s resume/skill set per matching) that appear in that round’s topics. Matching uses `skill_matching.normalize()` and case-insensitive comparison; a topic token/phrase matches if it normalizes to/contains the normalized missing skill (or the missing skill normalizes to a token in topic). Implementation should use `normalize` from `skill_matching`.

AI fallback path must also return `rounds` (empty or generated consistently if AI returns rounds, otherwise derived from stored rounds).
