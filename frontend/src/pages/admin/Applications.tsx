import { useEffect, useState } from "react";
import { api, httpError } from "../../api/client";
import type { AdminDriveRow, AppStatus, PaginatedApplications } from "../../api/types";
import { Alert, Button, Card, EmptyState, PageLoader, Select, StatusBadge } from "../../components/ui";
import { PageHeader } from "../../components/Layout";

const NEXT: Partial<Record<AppStatus, AppStatus[]>> = {
  applied: ["in_review", "rejected"],
  in_review: ["shortlisted", "rejected"],
  shortlisted: ["interview", "rejected"],
  interview: ["offered", "rejected"],
  offered: ["offer_accepted", "offer_declined"],
};

export default function AdminApplications() {
  const [data, setData] = useState<PaginatedApplications | null>(null);
  const [drives, setDrives] = useState<AdminDriveRow[]>([]);
  const [driveFilter, setDriveFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  useEffect(() => {
    void loadDrives();
  }, []);

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [driveFilter, statusFilter]);

  async function loadDrives() {
    try {
      const { data: d } = await api.get<AdminDriveRow[]>("/admin/drives");
      setDrives(d);
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    }
  }

  async function load() {
    try {
      setLoading(true);
      const { data: d } = await api.get<PaginatedApplications>("/admin/applications", {
        params: { limit: 100, drive_id: driveFilter || undefined, status: statusFilter || undefined },
      });
      setData(d);
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setLoading(false);
    }
  }

  async function setStatus(appId: string, newStatus: AppStatus) {
    setBusy(appId);
    setError(null);
    try {
      await api.patch(`/admin/applications/${appId}/status`, { new_status: newStatus });
      await load();
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(null);
    }
  }

  if (!data) {
    return error ? <Alert tone="error">{error}</Alert> : <PageLoader />;
  }

  return (
    <div>
      <PageHeader title="Applications" />
      {error ? <Alert tone="error">{error}</Alert> : null}

      <Card>
        <div className="row" style={{ marginBottom: 12 }}>
          <label className="field mb-0" style={{ minWidth: 240 }}>
            <span className="field-label">Drive</span>
            <Select value={driveFilter} onChange={(e) => setDriveFilter(e.target.value)}>
              <option value="">All drives</option>
              {drives.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.title}
                </option>
              ))}
            </Select>
          </label>
          <label className="field mb-0" style={{ minWidth: 200 }}>
            <span className="field-label">Status</span>
            <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
              <option value="">All statuses</option>
              {Object.keys(NEXT).map((s) => (
                <option key={s} value={s}>
                  {s.replace(/_/g, " ")}
                </option>
              ))}
            </Select>
          </label>
          <Button variant="secondary" onClick={load} disabled={loading}>
            Refresh
          </Button>
        </div>

        {loading ? (
          <PageLoader />
        ) : data.items.length === 0 ? (
          <EmptyState message="No applications match the filters." />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>Drive</th>
                  <th>Status</th>
                  <th>Applied</th>
                  <th>Move to</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <strong>{a.drive_title}</strong>
                      <div className="muted">{a.company_name}</div>
                    </td>
                    <td>
                      <StatusBadge status={a.status} />
                    </td>
                    <td>{new Date(a.applied_at).toLocaleString()}</td>
                    <td>
                      {NEXT[a.status]?.length ? (
                        <div className="row">
                          <Select
                            value=""
                            disabled={busy === a.id}
                            onChange={(e) => {
                              if (e.target.value) void setStatus(a.id, e.target.value as AppStatus);
                            }}
                            style={{ width: 150 }}
                          >
                            <option value="">Move…</option>
                            {NEXT[a.status]!.map((s) => (
                              <option key={s} value={s}>
                                {s.replace(/_/g, " ")}
                              </option>
                            ))}
                          </Select>
                        </div>
                      ) : (
                        <span className="muted">Final</span>
                      )}
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