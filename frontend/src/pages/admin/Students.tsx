import { ChangeEvent, useEffect, useState } from "react";
import { api, httpError } from "../../api/client";
import type { PaginatedStudents, StudentBrief, StudentImportResult } from "../../api/types";
import { Alert, Badge, Button, Card, EmptyState, Input, PageLoader } from "../../components/ui";
import { PageHeader } from "../../components/Layout";

export default function AdminStudents() {
  const [data, setData] = useState<PaginatedStudents | null>(null);
  const [query, setQuery] = useState("");
  const [importResult, setImportResult] = useState<StudentImportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    try {
      const { data: d } = await api.get<PaginatedStudents>("/admin/students", { params: { limit: 100 } });
      setData(d);
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    }
  }

  async function search() {
    setBusy(true);
    setError(null);
    try {
      const { data: d } = await api.get<PaginatedStudents>("/admin/students", {
        params: { limit: 100, q: query || undefined },
      });
      setData(d);
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(false);
    }
  }

  async function importCsv(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setBusy(true);
    setError(null);
    setImportResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post<StudentImportResult>("/admin/students/import", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setImportResult(data);
      await load();
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(false);
    }
  }

  async function toggleActive(student: StudentBrief) {
    setBusy(true);
    setError(null);
    try {
      await api.patch(`/admin/students/${student.id}`, { is_active: !student.is_active });
      await load();
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(false);
    }
  }

  if (!data) {
    return error ? <Alert tone="error">{error}</Alert> : <PageLoader />;
  }

  return (
    <div>
      <PageHeader title="Students" />
      {error ? <Alert tone="error">{error}</Alert> : null}

      <Card title="Import students (CSV)">
        <p className="muted" style={{ margin: "0 0 10px" }}>
          CSV columns: college_id, email, full_name, department_code, batch_year, cgpa, backlog_count,
          active_backlogs, gender, date_of_birth, phone.
        </p>
        <div className="row">
          <label className="btn btn-secondary btn-sm">
            {busy ? "Importing…" : "Choose CSV"}
            <input type="file" accept=".csv" hidden onChange={importCsv} />
          </label>
        </div>
        {importResult ? (
          <div className="stack" style={{ marginTop: 12 }}>
            <Alert tone="success">
              Created {importResult.created}, skipped {importResult.skipped}.
            </Alert>
            {importResult.failed.length > 0 ? (
              <div>
                <strong>Failures:</strong>
                <ul>
                  {importResult.failed.map((f, i) => (
                    <li key={i}>
                      {f.row}: {f.reason}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
            {importResult.activation_tokens.length > 0 ? (
              <div>
                <strong>Activation tokens (first run):</strong>
                <ul>
                  {importResult.activation_tokens.map((t) => (
                    <li key={t.email}>
                      {t.email} → <code>{t.token}</code>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : null}
      </Card>

      <Card
        title={`Students (${data.total})`}
        actions={
          <div className="row">
            <Input
              placeholder="Search by name / ID / email…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") void search();
              }}
              style={{ width: 260 }}
            />
            <Button variant="secondary" className="btn-sm" onClick={search} disabled={busy}>
              Search
            </Button>
          </div>
        }
      >
        {data.items.length === 0 ? (
          <EmptyState message="No students found." />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Student</th>
                  <th>Department</th>
                  <th>Batch</th>
                  <th>CGPA</th>
                  <th>Backlogs</th>
                  <th>Verified</th>
                  <th>Active</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((s) => (
                  <tr key={s.id}>
                    <td>
                      <strong>{s.full_name}</strong>
                      <div className="muted">
                        {s.college_id} · {s.email}
                      </div>
                    </td>
                    <td>{s.department_code}</td>
                    <td>{s.batch_year}</td>
                    <td>{s.cgpa ?? "—"}</td>
                    <td>
                      {s.backlog_count ?? "—"}
                      {s.active_backlogs ? ` (${s.active_backlogs} active)` : ""}
                    </td>
                    <td>
                      {s.academic_data_verified ? (
                        <Badge tone="good">Verified</Badge>
                      ) : (
                        <Badge tone="warn">Unverified</Badge>
                      )}
                    </td>
                    <td>
                      {s.is_active ? (
                        <Badge tone="good">Active</Badge>
                      ) : (
                        <Badge tone="bad">Suspended</Badge>
                      )}
                    </td>
                    <td>
                      <Button
                        variant="secondary"
                        className="btn-sm"
                        onClick={() => void toggleActive(s)}
                        disabled={busy}
                      >
                        {s.is_active ? "Suspend" : "Reactivate"}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}