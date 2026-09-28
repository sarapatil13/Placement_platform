import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, httpError } from "../../api/client";
import type {
  BulkEvaluateResult,
  DriveRead,
  EligibilityRuleIn,
  JDExtractionSuggestion,
} from "../../api/types";
import { Alert, Badge, Button, Card, Field, Input, PageLoader, Select, Tag, Textarea } from "../../components/ui";
import { PageHeader } from "../../components/Layout";
import { DriveCriteriaEditor } from "../../components/DriveCriteriaEditor";
import { criterionLabel } from "../../lib/criteria";

interface EditForm {
  title: string;
  role_title: string;
  description: string;
  employment_type: string;
  location: string;
  ctc_lpa: string;
  stipend: string;
  apply_by: string;
  drive_date: string;
  status: string;
  required_skills_text: string;
}

function toForm(d: DriveRead): EditForm {
  return {
    title: d.title,
    role_title: d.role_title,
    description: d.description ?? "",
    employment_type: d.employment_type,
    location: d.location ?? "",
    ctc_lpa: d.ctc_lpa ?? "",
    stipend: d.stipend ?? "",
    apply_by: d.apply_by ?? "",
    drive_date: d.drive_date ?? "",
    status: d.status,
    required_skills_text: d.required_skills.join(", "),
  };
}

export default function AdminDriveDetail() {
  const { driveId } = useParams<{ driveId: string }>();
  const [drive, setDrive] = useState<DriveRead | null>(null);
  const [form, setForm] = useState<EditForm | null>(null);
  const [criteria, setCriteria] = useState<EligibilityRuleIn[]>([]);
  const [suggestion, setSuggestion] = useState<JDExtractionSuggestion | null>(null);
  const [jdFilename, setJdFilename] = useState<string | null>(null);
  const [evaluation, setEvaluation] = useState<BulkEvaluateResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    if (!driveId) return;
    void load();
  }, [driveId]);

  async function load() {
    if (!driveId) return;
    try {
      const { data } = await api.get<DriveRead>(`/drives/${driveId}`);
      setDrive(data);
      setForm(toForm(data));
      setCriteria(
        data.criteria.map((c) => ({
          criterion_type: c.criterion_type,
          parameters: c.parameters,
        })),
      );
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    }
  }

  function update<K extends keyof EditForm>(key: K, v: string) {
    setForm((f) => (f ? { ...f, [key]: v } : f));
  }

  async function saveFields(e: FormEvent) {
    e.preventDefault();
    if (!form || !driveId) return;
    setBusy("fields");
    setError(null);
    setSuccess(null);
    try {
      await api.patch(`/admin/drives/${driveId}`, {
        title: form.title,
        role_title: form.role_title,
        description: form.description || null,
        employment_type: form.employment_type,
        location: form.location || null,
        ctc_lpa: form.ctc_lpa || null,
        stipend: form.stipend || null,
        apply_by: form.apply_by ? new Date(form.apply_by).toISOString() : null,
        drive_date: form.drive_date ? new Date(form.drive_date).toISOString() : null,
        status: form.status,
      });
      setSuccess("Drive details saved.");
      await load();
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(null);
    }
  }

  async function saveCriteria() {
    if (!driveId) return;
    setBusy("criteria");
    setError(null);
    setSuccess(null);
    try {
      const skills = form?.required_skills_text
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean) ?? [];
      await api.patch(`/admin/drives/${driveId}`, { criteria, required_skills: skills });
      setSuccess("Eligibility criteria saved.");
      await load();
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(null);
    }
  }

  async function uploadJd(file: File) {
    if (!driveId) return;
    setBusy("jd");
    setError(null);
    setSuccess(null);
    setSuggestion(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post<{
        drive_id: string;
        filename: string;
        extracted: JDExtractionSuggestion;
        needs_confirmation: boolean;
      }>(`/admin/drives/${driveId}/jd`, fd, { headers: { "Content-Type": "multipart/form-data" } });
      setSuggestion(data.extracted);
      setJdFilename(data.filename);
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(null);
    }
  }

  function applySuggestion() {
    if (!suggestion) return;
    setForm((f) =>
      f
        ? {
            ...f,
            role_title: suggestion.role_title ?? f.role_title,
            location: suggestion.location ?? f.location,
            employment_type: suggestion.employment_type ?? f.employment_type,
            ctc_lpa: suggestion.ctc_lpa ?? f.ctc_lpa,
            stipend: suggestion.stipend ?? f.stipend,
            apply_by: suggestion.apply_by ?? f.apply_by,
            drive_date: suggestion.drive_date ?? f.drive_date,
            description: suggestion.description_summary ?? f.description,
            required_skills_text: suggestion.required_skills.join(", "),
          }
        : f,
    );
    if (suggestion.suggested_criteria.length > 0) setCriteria(suggestion.suggested_criteria);
  }

  async function confirmJd() {
    if (!driveId) return;
    setBusy("confirm");
    setError(null);
    setSuccess(null);
    try {
      const skills =
        suggestion?.required_skills ??
        form?.required_skills_text
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean) ??
        [];
      await api.post(`/admin/drives/${driveId}/jd/confirm`, {
        criteria: criteria.length > 0 ? criteria : suggestion?.suggested_criteria ?? [],
        required_skills: skills,
      });
      setSuggestion(null);
      setSuccess("JD extraction confirmed. Eligibility criteria finalised.");
      await load();
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(null);
    }
  }

  async function evaluate() {
    if (!driveId) return;
    setBusy("evaluate");
    setError(null);
    setSuccess(null);
    try {
      const { data } = await api.post<BulkEvaluateResult>(`/admin/drives/${driveId}/eligibility/evaluate`);
      setEvaluation(data);
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(null);
    }
  }

  async function publish() {
    if (!driveId) return;
    setBusy("publish");
    setError(null);
    setSuccess(null);
    try {
      await api.post(`/admin/drives/${driveId}/publish`, {});
      setSuccess("Drive published. Eligible students notified.");
      await load();
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(null);
    }
  }

  if (!drive || !form) {
    return error ? (
      <div>
        <Alert tone="error">{error}</Alert>
        <Link to="/app/admin/drives">← Back to drives</Link>
      </div>
    ) : (
      <PageLoader />
    );
  }

  return (
    <div>
      <PageHeader
        title={drive.title}
        actions={
          <Link to="/app/admin/drives">
            <Button variant="secondary" className="btn-sm">← Back</Button>
          </Link>
        }
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      {success ? <Alert tone="success">{success}</Alert> : null}

      <div className="row" style={{ marginBottom: 16 }}>
        <Badge tone={drive.status === "published" ? "good" : drive.status === "draft" ? "warn" : "neutral"}>
          Status: {drive.status}
        </Badge>
        <Badge tone={drive.eligibility_confirmed ? "good" : "warn"}>
          {drive.eligibility_confirmed ? "Eligibility confirmed" : "Eligibility not confirmed"}
        </Badge>
        {drive.is_ai_extraction_pending ? <Badge tone="info">AI JD extraction pending</Badge> : null}
        <Badge tone="neutral">{drive.applied_count} applications</Badge>
      </div>

      <Card title="Details" actions={drive.status === "draft" ? (
        <Button onClick={publish} disabled={busy === "publish"}>{busy === "publish" ? "Publishing…" : "Publish"}</Button>
      ) : undefined}>
        <form onSubmit={saveFields} className="mb-block">
          <div className="form-grid">
            <Field label="Title">
              <Input required minLength={3} value={form.title} onChange={(e) => update("title", e.target.value)} />
            </Field>
            <Field label="Role title">
              <Input value={form.role_title} onChange={(e) => update("role_title", e.target.value)} />
            </Field>
            <Field label="Employment type">
              <Select value={form.employment_type} onChange={(e) => update("employment_type", e.target.value)}>
                <option value="full_time">Full-time</option>
                <option value="internship">Internship</option>
                <option value="contract">Contract</option>
                <option value="part_time">Part-time</option>
              </Select>
            </Field>
            <Field label="Location">
              <Input value={form.location} onChange={(e) => update("location", e.target.value)} />
            </Field>
            <Field label="CTC (LPA)">
              <Input value={form.ctc_lpa} onChange={(e) => update("ctc_lpa", e.target.value)} />
            </Field>
            <Field label="Stipend">
              <Input value={form.stipend} onChange={(e) => update("stipend", e.target.value)} />
            </Field>
            <Field label="Apply by">
              <Input type="datetime-local" value={form.apply_by.slice(0, 16)} onChange={(e) => update("apply_by", e.target.value)} />
            </Field>
            <Field label="Drive date">
              <Input type="datetime-local" value={form.drive_date.slice(0, 16)} onChange={(e) => update("drive_date", e.target.value)} />
            </Field>
            <Field label="Status">
              <Select value={form.status} onChange={(e) => update("status", e.target.value)}>
                <option value="draft">Draft</option>
                <option value="published">Published</option>
                <option value="closed">Closed</option>
                <option value="archived">Archived</option>
              </Select>
            </Field>
          </div>
          <Field label="Description">
            <Textarea value={form.description} onChange={(e) => update("description", e.target.value)} />
          </Field>
          <div className="form-actions">
            <Button type="submit" disabled={busy === "fields"}>
              {busy === "fields" ? "Saving…" : "Save details"}
            </Button>
          </div>
        </form>
      </Card>

      <Card title="Eligibility criteria">
        <Field label="Required skills (comma separated)">
          <Input
            value={form.required_skills_text}
            onChange={(e) => update("required_skills_text", e.target.value)}
          />
        </Field>
        <DriveCriteriaEditor value={criteria} onChange={setCriteria} />
        <div className="form-actions">
          <Button variant="secondary" onClick={saveCriteria} disabled={busy === "criteria"}>
            {busy === "criteria" ? "Saving…" : "Save criteria"}
          </Button>
        </div>
      </Card>

      <Card title="AI job-description extraction">
        <div className="row">
          <label className="btn btn-secondary btn-sm">
            {busy === "jd" ? "Uploading…" : jdFilename ?? "Upload JD (PDF/DOCX/TXT)"}
            <input
              type="file"
              accept=".pdf,.docx,.txt"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void uploadJd(f);
                e.target.value = "";
              }}
            />
          </label>
        </div>
        {suggestion ? (
          <div className="stack" style={{ marginTop: 16 }}>
            <Alert tone="warn">
              These are AI suggestions — review before confirming. Nothing is applied until you confirm.
            </Alert>
            <div className="kv">
              <dt>Role</dt>
              <dd>{suggestion.role_title ?? "—"}</dd>
              <dt>Location</dt>
              <dd>{suggestion.location ?? "—"}</dd>
              <dt>Employment</dt>
              <dd>{suggestion.employment_type ?? "—"}</dd>
              <dt>CTC</dt>
              <dd>{suggestion.ctc_lpa ?? "—"}</dd>
              <dt>Stipend</dt>
              <dd>{suggestion.stipend ?? "—"}</dd>
              <dt>Summary</dt>
              <dd>{suggestion.description_summary ?? "—"}</dd>
            </div>
            <strong>Suggested criteria</strong>
            {suggestion.suggested_criteria.length === 0 ? (
              <p className="rule-note mb-0">None suggested.</p>
            ) : (
              <div className="skill-chips">
                {suggestion.suggested_criteria.map((c, i) => (
                  <Tag key={i}>
                    {criterionLabel(c.criterion_type)} {c.parameters ? describeSuggestion(c) : ""}
                  </Tag>
                ))}
              </div>
            )}
            <div className="row">
              <Button variant="secondary" onClick={applySuggestion}>
                Apply suggestions to form
              </Button>
              <Button onClick={confirmJd} disabled={busy === "confirm"}>
                {busy === "confirm" ? "Confirming…" : "Confirm & finalise criteria"}
              </Button>
            </div>
          </div>
        ) : null}
      </Card>

      <Card title="Bulk eligibility evaluation">
        <p className="muted mb-0" style={{ marginBottom: 10 }}>
          Run the deterministic eligibility engine across all students against the current criteria.
        </p>
        <Button variant="secondary" onClick={evaluate} disabled={busy === "evaluate"}>
          {busy === "evaluate" ? "Evaluating…" : "Run evaluation"}
        </Button>
        {evaluation ? (
          <div className="stack" style={{ marginTop: 16 }}>
            <div className="stat-grid">
              <div className="stat-card"><div className="stat-label">Total students</div><div className="stat-value">{evaluation.total}</div></div>
              <div className="stat-card"><div className="stat-label">Eligible</div><div className="stat-value">{evaluation.eligible}</div></div>
              <div className="stat-card"><div className="stat-label">Ineligible</div><div className="stat-value">{evaluation.ineligible_count}</div></div>
              <div className="stat-card"><div className="stat-label">Inconclusive</div><div className="stat-value">{evaluation.inconclusive}</div></div>
            </div>
          </div>
        ) : null}
      </Card>
    </div>
  );
}

function describeSuggestion(c: { parameters?: Record<string, unknown> }): string {
  if (!c.parameters) return "";
  const v = c.parameters["value"] ?? c.parameters["active_backlogs"];
  if (typeof v === "number") return String(v);
  return "";
}