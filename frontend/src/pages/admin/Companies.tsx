import { FormEvent, useEffect, useState } from "react";
import { api, httpError } from "../../api/client";
import type { CompanyCreateBody, PaginatedCompanies } from "../../api/types";
import { Alert, Button, Card, EmptyState, Field, Input, PageLoader } from "../../components/ui";
import { PageHeader } from "../../components/Layout";

interface Draft extends CompanyCreateBody {
  id?: string;
}

const EMPTY_DRAFT: Draft = {
  name: "",
  website: "",
  industry: "",
  about: "",
  location: "",
  contact_email: "",
  contact_name: "",
  tiers: [],
};

export default function AdminCompanies() {
  const [companies, setCompanies] = useState<PaginatedCompanies | null>(null);
  const [draft, setDraft] = useState<Draft>(EMPTY_DRAFT);
  const [editing, setEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    try {
      const { data: d } = await api.get<PaginatedCompanies>("/admin/companies", { params: { limit: 100 } });
      setCompanies(d);
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    }
  }

  function update<K extends keyof Draft>(key: K, v: string) {
    setDraft((d) => ({ ...d, [key]: v }));
  }

  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setSuccess(null);
    try {
      const body: CompanyCreateBody = {
        name: draft.name,
        website: draft.website || undefined,
        industry: draft.industry || undefined,
        about: draft.about || undefined,
        location: draft.location || undefined,
        contact_email: draft.contact_email,
        contact_name: draft.contact_name || undefined,
        tiers: draft.tiers ?? [],
      };
      if (draft.id) {
        await api.patch(`/admin/companies/${draft.id}`, body);
        setSuccess("Company updated.");
      } else {
        await api.post("/admin/companies", body);
        setSuccess("Company created.");
      }
      setDraft(EMPTY_DRAFT);
      setEditing(false);
      await load();
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(false);
    }
  }

  function startEdit(c: PaginatedCompanies["items"][number]) {
    setEditing(true);
    setDraft({
      id: c.id,
      name: c.name,
      website: c.website ?? "",
      industry: c.industry ?? "",
      about: c.about ?? "",
      location: c.location ?? "",
      contact_email: c.contact_email,
      contact_name: c.contact_name ?? "",
      tiers: c.tiers ?? [],
    });
  }

  if (!companies) {
    return error ? <Alert tone="error">{error}</Alert> : <PageLoader />;
  }

  return (
    <div>
      <PageHeader
        title="Companies"
        actions={
          <Button onClick={() => {
            setEditing(false);
            setDraft(EMPTY_DRAFT);
          }}>
            + New company
          </Button>
        }
      />
      {error ? <Alert tone="error">{error}</Alert> : null}
      {success ? <Alert tone="success">{success}</Alert> : null}

      {draft.name !== "" || editing ? (
        <Card title={editing ? "Edit company" : "New company"}>
          <form onSubmit={save}>
            <div className="form-grid">
              <Field label="Name">
                <Input required minLength={2} value={draft.name} onChange={(e) => update("name", e.target.value)} />
              </Field>
              <Field label="Industry">
                <Input value={draft.industry ?? ""} onChange={(e) => update("industry", e.target.value)} />
              </Field>
              <Field label="Website">
                <Input value={draft.website ?? ""} onChange={(e) => update("website", e.target.value)} />
              </Field>
              <Field label="Location">
                <Input value={draft.location ?? ""} onChange={(e) => update("location", e.target.value)} />
              </Field>
              <Field label="Contact email">
                <Input type="email" required value={draft.contact_email} onChange={(e) => update("contact_email", e.target.value)} />
              </Field>
              <Field label="Contact name">
                <Input value={draft.contact_name ?? ""} onChange={(e) => update("contact_name", e.target.value)} />
              </Field>
            </div>
            <Field label="About">
              <Input value={draft.about ?? ""} onChange={(e) => update("about", e.target.value)} />
            </Field>
            <div className="form-actions">
              <Button type="submit" disabled={busy}>
                {busy ? "Saving…" : editing ? "Update" : "Create"}
              </Button>
              <Button
                variant="secondary"
                type="button"
                onClick={() => {
                  setDraft(EMPTY_DRAFT);
                  setEditing(false);
                }}
              >
                Cancel
              </Button>
            </div>
          </form>
        </Card>
      ) : null}

      {companies.items.length === 0 ? (
        <EmptyState message="No companies yet. Add your first recruiter." />
      ) : (
        <Card>
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Company</th>
                  <th>Industry</th>
                  <th>Location</th>
                  <th>Contact</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {companies.items.map((c) => (
                  <tr key={c.id}>
                    <td>
                      <strong>{c.name}</strong>
                      <div className="muted">{c.website}</div>
                    </td>
                    <td>{c.industry ?? "—"}</td>
                    <td>{c.location ?? "—"}</td>
                    <td>
                      <div>{c.contact_email}</div>
                      <div className="muted">{c.contact_name}</div>
                    </td>
                    <td>
                      <Button variant="secondary" className="btn-sm" onClick={() => startEdit(c)}>
                        Edit
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}