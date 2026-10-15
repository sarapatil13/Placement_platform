export interface WhoAmI {
  id: string;
  full_name: string;
  email: string;
  role: string;
  institution_id: string;
  institution_code: string;
  is_active: boolean;
  must_change_password: boolean;
}

export interface AccessToken {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: WhoAmI;
}

export interface TokenPair extends AccessToken {
  refresh_token: string;
}

export interface ApiMessage {
  message: string;
}

export interface MessageResponse {
  message: string;
}

export interface Pagination {
  total: number;
  page: number;
  limit: number;
}

// ---------------------------------------------------------------- students

export interface SkillRead {
  id: string;
  name: string;
  normalized_name: string;
  category?: string;
  proficiency?: number;
  years_experience?: number;
  source?: string;
  is_verified: boolean;
}

export interface StudentDetail {
  id: string;
  user_id: string;
  college_id: string;
  full_name: string;
  email: string;
  batch_year: number;
  department_code: string;
  department_name: string;
  cgpa?: number;
  backlog_count?: number;
  active_backlogs?: number;
  academic_data_verified: boolean;
  is_active: boolean;
  profile_headline?: string;
  about?: string;
  phone?: string;
  location?: string;
  portfolio_url?: string;
  linkedin_url?: string;
  github_url?: string;
  gender?: string;
  date_of_birth?: string;
}

export interface StudentBrief {
  id: string;
  user_id: string;
  college_id: string;
  full_name: string;
  email: string;
  batch_year: number;
  department_code: string;
  department_name: string;
  cgpa?: number;
  backlog_count?: number;
  active_backlogs?: number;
  academic_data_verified: boolean;
  is_active: boolean;
}

export interface PaginatedStudents extends Pagination {
  items: StudentBrief[];
}

// ----------------------------------------------------------------- companies

export interface CompanyCreateBody {
  name: string;
  website?: string;
  industry?: string;
  about?: string;
  logo_url?: string;
  location?: string;
  contact_email: string;
  contact_name?: string;
  tiers?: string[];
}

export interface CompanyUpdateBody extends Partial<Omit<CompanyCreateBody, "contact_email">> {
  contact_email?: string;
  reputation_score?: number;
  is_active?: boolean;
}

export interface CompanyRead {
  id: string;
  name: string;
  website?: string;
  industry?: string;
  about?: string;
  location?: string;
  contact_email: string;
  contact_name?: string;
  tiers: string[];
  reputation_score?: number;
  is_active: boolean;
  created_at: string;
}

export interface PaginatedCompanies extends Pagination {
  items: CompanyRead[];
}

// ------------------------------------------------------------------- drives

export type CriterionType =
  | "cgpa_min"
  | "cgpa_max"
  | "backlog_max"
  | "departments"
  | "batch_years"
  | "skill_min_match"
  | "age_max"
  | "gender"
  | "percentile_min";

export interface EligibilityRuleIn {
  criterion_type: string;
  parameters: Record<string, unknown>;
}

export interface EligibilityRuleOut {
  id: string;
  criterion_type: string;
  parameters: Record<string, unknown>;
  source: string;
  is_active: boolean;
  confirmed_by?: string;
  confirmed_at?: string;
  created_at: string;
}

export type DriveStatus = "draft" | "published" | "closed" | "archived";

export interface DriveRead {
  id: string;
  company_id: string;
  company_name: string;
  title: string;
  role_title: string;
  description?: string;
  employment_type: string;
  location?: string;
  ctc_lpa?: string;
  stipend?: string;
  status: DriveStatus;
  eligibility_confirmed: boolean;
  is_ai_extraction_pending: boolean;
  applied_count: number;
  published_at?: string;
  apply_by?: string;
  drive_date?: string;
  created_at: string;
  updated_at: string;
  criteria: EligibilityRuleOut[];
  required_skills: string[];
}

export interface PaginatedDrives extends Pagination {
  items: DriveRead[];
}

export interface DriveCreateBody {
  company_id: string;
  title: string;
  role_title?: string;
  description?: string;
  employment_type?: string;
  location?: string;
  ctc_lpa?: string;
  stipend?: string;
  apply_by?: string;
  drive_date?: string;
  status?: DriveStatus;
  criteria?: EligibilityRuleIn[];
  required_skills?: string[];
}

export interface DriveUpdateBody extends Partial<DriveCreateBody> {
  status?: DriveStatus;
}

export interface DriveEligibilityCheck {
  drive_id: string;
  eligible: boolean;
  score: number;
  reason: string;
  exact_reasons: string[];
  failed_rules: Record<string, unknown>[];
  passed_rules: Record<string, unknown>[];
  evaluated_at: string;
}

export interface AdminDriveRow {
  id: string;
  title: string;
  company_name: string;
  status: DriveStatus;
  eligibility_confirmed: boolean;
  is_ai_extraction_pending: boolean;
  applied_count: number;
  created_at: string;
}

export type RoundType =
  | "online_assessment"
  | "technical_interview"
  | "hr_interview"
  | "group_discussion"
  | "other";

export interface DriveRound {
  id: string;
  position: number;
  round_type: RoundType;
  title: string;
  topics: string[];
  scheduled_at?: string;
}

export interface DriveRoundIn {
  position: number;
  round_type: RoundType;
  title: string;
  topics: string[];
  scheduled_at?: string;
}

export interface JDExtractionSuggestion {
  company_name?: string;
  role_title?: string;
  location?: string;
  employment_type?: string;
  ctc_lpa?: string;
  stipend?: string;
  apply_by?: string;
  drive_date?: string;
  description_summary?: string;
  required_skills: string[];
  suggested_criteria: EligibilityRuleIn[];
}

export interface JDUploadResponse {
  drive_id: string;
  filename: string;
  extracted: JDExtractionSuggestion;
  needs_confirmation: boolean;
}

export interface BulkEvaluateResult {
  drive_id: string;
  total: number;
  eligible: number;
  ineligible_count: number;
  inconclusive: number;
  eligible_ids: string[];
  ineligible: Record<string, unknown>[];
}

// -------------------------------------------------------------- applications

export type AppStatus =
  | "applied"
  | "in_review"
  | "shortlisted"
  | "interview"
  | "offered"
  | "rejected"
  | "withdrawn"
  | "offer_accepted"
  | "offer_declined";

export interface ApplicationRead {
  id: string;
  student_id: string;
  drive_id: string;
  drive_title: string;
  company_name: string;
  status: AppStatus;
  eligibility_snapshot: Record<string, unknown>;
  applied_at: string;
  updated_at: string;
  cover_note?: string;
  withdrawn_reason?: string;
}

export interface StatusHistoryRow {
  id: string;
  from_status?: string;
  to_status: AppStatus;
  changed_by?: string;
  changed_by_role?: string;
  note?: string;
  is_student_initiated: boolean;
  created_at: string;
}

export interface ApplicationDetail extends ApplicationRead {
  eligibility_evaluated: boolean;
  resume_filename?: string;
  status_history: StatusHistoryRow[];
}

export interface PaginatedApplications extends Pagination {
  items: ApplicationRead[];
}

// ------------------------------------------------------------ notifications

export interface NotificationRead {
  id: string;
  type: string;
  title: string;
  body: string;
  link?: string;
  payload: Record<string, unknown>;
  is_read: boolean;
  created_at: string;
}

export interface PaginatedNotifications extends Pagination {
  items: NotificationRead[];
  unread_count: number;
}

// --------------------------------------------------------------- dashboard

export interface DashboardDriveItem {
  drive_id: string;
  title: string;
  company_name: string;
  location?: string;
  apply_by?: string;
  days_left?: number;
}

export interface SkillGapCount {
  skill: string;
  drives: number;
}

export interface StudentDashboard {
  eligible_open_drives: DashboardDriveItem[];
  closing_soon: DashboardDriveItem[];
  application_counts_by_status: Partial<Record<AppStatus, number>>;
  total_applications: number;
  top_skill_gaps: SkillGapCount[];
}

// ------------------------------------------------------------------ resumes

export interface ResumeMetadata {
  id: string;
  filename: string;
  mime_type: string;
  size_bytes: number;
  parse_status: string;
  is_primary: boolean;
  created_at: string;
}

export interface ResumeUploadResponse {
  resume: ResumeMetadata;
  message: string;
}

export interface ResumeDetail extends ResumeMetadata {
  sha256: string;
  parsed_skills: string[];
  extracted_text?: string;
  parse_error?: string;
}

export interface ResumeAnalysisResult {
  skill_match: number;
  matched_skills: string[];
  partial_skills: string[];
  missing_skills: string[];
  resume_skills_detected: string[];
  drive_required_skills: string[];
  skill_gap_analysis: Record<string, string>[];
  feedback_text?: string;
  summary?: string;
  analyzed_at: string;
}

export interface SkillGapItem {
  skill: string;
  status: "matched" | "partial" | "missing";
  recommendation: string;
}

export interface RoadmapRound {
  round_id: string;
  position: number;
  round_type: RoundType;
  title: string;
  topics: string[];
  scheduled_at?: string;
  focus_skills: string[];
}

export interface PreparationRoadmap {
  drive_id: string;
  skill_gaps: SkillGapItem[];
  rounds: RoadmapRound[];
  roadmap_steps: string[];
  suggested_practice: string[];
  disclaimer: string;
}

// ---------------------------------------------------------------- analytics

export interface AnalyticsSummary {
  total_students: number;
  total_drives: number;
  published_drives: number;
  total_applications: number;
  unique_applicants: number;
  applications_per_drive: number;
  overall_funnel: { label: string; count: number }[];
  department_stats: {
    department_code: string;
    department_name: string;
    students: number;
    applications: number;
    placed: number;
  }[];
  status_stats: { status: string; count: number }[];
  top_drives: {
    drive_id: string;
    drive_title: string;
    company_name: string;
    apps_total: number;
    apps_shortlisted: number;
    apps_offered: number;
  }[];
}

// -------------------------------------------------------------------- audit

export interface AuditRow {
  id: string;
  actor_id?: string;
  actor_email?: string;
  actor_role?: string;
  action: string;
  entity_type?: string;
  entity_id?: string;
  outcome: string;
  ip_address?: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface PaginatedAudit extends Pagination {
  items: AuditRow[];
}

// ------------------------------------------------------------- admin helpers

export interface StudentImportResult {
  created: number;
  skipped: number;
  failed: { row: string; reason: string }[];
  activation_tokens: { email: string; token: string }[];
}