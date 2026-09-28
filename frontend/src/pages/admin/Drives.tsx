import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, httpError } from "../../api/client";
import type { AdminDriveRow, CompanyRead, DriveCreateBody, PaginatedCompanies } from "../../api/types";
import { Alert, Badge, Button, Card, EmptyState, Field, Input, PageLoader, Select, Textarea } from "../../components/ui";
import { PageHeader } from "../../components/Layout";
import { DriveCriteriaEditor } from "../../components/DriveCriteriaEditor";

interface Draft {
  company_id: string;
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

const INITIAL_DRAFT: Draft = {
  company_id: "",
  title: "",
  role_title: "",
  description: "",
  employment_type: "full_time",
  location: "",
  ctc_lpa: "",
  stipend: "",
  apply_by: "",
  drive_date: "",
  status: "draft",
  required_skills_text: "",
};

export default function AdminDrives() {
  const [drives, setDrives] = useState<AdminDriveRow[] | null>(null);
  const [companies, setCompanies] = useState<CompanyRead[]>([]);
  const [draft, setDraft] = useState<Draft>(INITIAL_DRAFT);
  const [criteria, setCriteria] = useState<DriveCreateBody["criteria"]>([]);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    try {
      const [d, c] = await Promise.all([
        api.get<AdminDriveRow[]>("/admin/drives"),
        api.get<PaginatedCompanies>("/admin/companies", { params: { limit: 100 } }),
      ]);
      setDrives(d.data);
      setCompanies(c.data.items);
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    }
  }

  function update<K extends keyof Draft>(key: K, v: string) {
    setDraft((d) => ({ ...d, [key]: v }));
  }

  async function createDrive(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const body: DriveCreateBody = {
        company_id: draft.company_id,
        title: draft.title,
        role_title: draft.role_title || undefined,
        description: draft.description || undefined,
        employment_type: draft.employment_type || "full_time",
        location: draft.location || undefined,
        ctc_lpa: draft.ctc_lpa || undefined,
        stipend: draft.stipend || undefined,
        apply_by: draft.apply_by ? new Date(draft.apply_by).toISOString() : undefined,
        drive_date: draft.drive_date ? new Date(draft.drive_date).toISOString() : undefined,
        status: (draft.status as DriveCreateBody["status"]) ?? "draft",
        criteria,
        required_skills: draft.required_skills_text
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      };
      await api.post<{ id: string; status: string }>("/admin/drives", body);
      setSuccess("Drive created.");
      setDraft(INITIAL_DRAFT);
      setCriteria([]);
      setShowForm(false);
      await load();
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(false);
    }
  }

  async function publish(id: string) {
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      await api.post(`/admin/drives/${id}/publish`, {});
      setSuccess("Drive published. Eligible students were notified.");
      await load();
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(false);
    }
  }

  async function changeStatus(id: string, status: string) {
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      await api.patch(`/admin/drives/${id}`, { status });
      setSuccess("Status updated.");
      await load();
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(false);
    }
  }

  if (!drives) {
    return error ? <Alert tone="error">{error}</Alert> : <PageLoader />;
  }

  return (
    <div>
      <PageHeader
        title="Manage Drives"
        actions={
          <Button onClick={() => setShowForm((v) => !v)}>{showForm ? "Cancel" : "+ New drive"}</Button>
        }
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      {success ? <Alert tone="success">{success}</Alert> : null}

      {showForm ? (
        <Card title="New drive">
          <form onSubmit={createDrive}>
            <div className="form-grid">
              <Field label="Company">
                <Select required value={draft.company_id} onChange={(e) => update("company_id", e.target.value)}>
                  <option value="">Select company…</option>
                  {companies.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.name}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="Status">
                <Select value={draft.status} onChange={(e) => update("status", e.target.value)}>
                  <option value="draft">Draft</option>
                  <option value="published">Published</option>
                  <option value="closed">Closed</option>
                  <option value="archived">Archived</option>
                </Select>
              </Field>
              <Field label="Title">
                <Input required minLength={3} value={draft.title} onChange={(e) => update("title", e.target.value)} />
              </Field>
              <Field label="Role title">
                <Input value={draft.role_title} onChange={(e) => update("role_title", e.target.value)} />
              </Field>
              <Field label="Employment type">
                <Select value={draft.employment_type} onChange={(e) => update("employment_type", e.target.value)}>
                  <option value="full_time">Full-time</option>
                  <option value="internship">Internship</option>
                  <option value="contract">Contract</option>
                  <option value="part_time">Part-time</option>
                </Select>
              </Field>
              <Field label="Location">
                <Input value={draft.location} onChange={(e) => update("location", e.target.value)} />
              </Field>
              <Field label="CTC (LPA)">
                <Input value={draft.ctc_lpa} onChange={(e) => update("ctc_lpa", e.target.value)} />
              </Field>
              <Field label="Stipend">
                <Input value={draft.stipend} onChange={(e) => update("stipend", e.target.value)} />
              </Field>
              <Field label="Apply by">
                <Input type="datetime-local" value={draft.apply_by} onChange={(e) => update("apply_by", e.target.value)} />
              </Field>
              <Field label="Drive date">
                <Input type="datetime-local" value={draft.drive_date} onChange={(e) => update("drive_date", e.target.value)} />
              </Field>
            </div>
            <Field label="Required skills (comma separated)">
              <Input value={draft.required_skills_text} onChange={(e) => update("required_skills_text", e.target.value)} />
            </Field>
            <Field label="Description">
              <Textarea value={draft.description} onChange={(e) => update("description", e.target.value)} />
            </Field>
            <Field label="Eligibility criteria">
              <DriveCriteriaEditor value={criteria ?? []} onChange={setCriteria} />
            </Field>
            <div className="form-actions">
              <Button type="submit" disabled={busy}>
                {busy ? "Creating…" : "Create drive"}
              </Button>
            </div>
          </form>
        </Card>
      ) : null}

      {drives.length === 0 ? (
        <EmptyState message="No drives yet. Create your first one." />
      ) : (
        <Card>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Drive</th>
                  <th>Status</th>
                  <th>Eligibility</th>
                  <th>Apps</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {drives.map((d) => (
                  <tr key={d.id}>
                    <td>
                      <strong>{d.title}</strong>
                      <div className="muted">{d.company_name}</div>
                    </td>
                    <td>
                      <Badge tone={d.status === "published" ? "good" : d.status === "draft" ? "warn" : "neutral"}>
                        {d.status}
                      </Badge>
                    </td>
                    <td>
                      {d.eligibility_confirmed ? (
                        <Badge tone="good">Confirmed</Badge>
                      ) : d.is_ai_extraction_pending ? (
                        <Badge tone="warn">JD pending</Badge>
                      ) : (
                        <Badge tone="neutral">Not set</Badge>
                      )}
                    </td>
                    <td>{d.applied_count}</td>
                    <td>{new Date(d.created_at).toLocaleDateString()}</td>
                    <td>
                      <div className="row">
                        <Link to={`/app/admin/drives/${d.id}`}>
                          <Button variant="secondary" className="btn-sm">Manage</Button>
                        </Link>
                        {d.status === "draft" ? (
                          <>
                            <Button className="btn-sm" onClick={() => publish(d.id)} disabled={busy}>
                              Publish
                            </Button>
                            <Button variant="danger" className="btn-sm" onClick={() => changeStatus(d.id, "archived")} disabled={busy}>
                              Archive
                            </Button>
                          </>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
      {companies.length === 0 ? (
        <Alert tone="warn">
          No companies on file — add one under Companies before creating a drive.
        </Alert>
      ) : null}
    </div>
  );
}