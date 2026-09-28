import { useEffect, useState } from "react";
import { api, httpError } from "../../api/client";
import type { PaginatedAudit } from "../../api/types";
import { Alert, Card, EmptyState, PageLoader, Select } from "../../components/ui";
import { PageHeader } from "../../components/Layout";

export default function AdminAudit() {
  const [data, setData] = useState<PaginatedAudit | null>(null);
  const [action, setAction] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void load();
  }, [action]);

  async function load() {
    try {
      const { data: d } = await api.get<PaginatedAudit>("/admin/audit-log", {
        params: { limit: 100, action: action || undefined },
      });
      setData(d);
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    }
  }

  if (!data) {
    return error ? <Alert tone="error">{error}</Alert> : <PageLoader />;
  }

  const actions = Array.from(new Set(data.items.map((r) => r.action))).sort();

  return (
    <div>
      <PageHeader title="Audit Log" />
      {error ? <Alert tone="error">{error}</Alert> : null}

      <Card
        title={`Events (${data.total})`}
        actions={
          <Select value={action} onChange={(e) => setAction(e.target.value)} style={{ width: 220 }}>
            <option value="">All actions</option>
            {actions.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </Select>
        }
      >
        {data.items.length === 0 ? (
          <EmptyState message="No audit events recorded." />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Actor</th>
                  <th>Action</th>
                  <th>Target</th>
                  <th>Outcome</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((r) => (
                  <tr key={r.id}>
                    <td>{new Date(r.created_at).toLocaleString()}</td>
                    <td>
                      <div>{r.actor_email ?? "—"}</div>
                      <div className="muted">{r.actor_role}</div>
                    </td>
                    <td>{r.action}</td>
                    <td>
                      {r.entity_type ? (
                        <>
                          {r.entity_type} · {r.entity_id ?? ""}
                        </>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td>{r.outcome}</td>
                    <td>
                      {Object.keys(r.detail).length > 0 ? (
                        <code style={{ fontSize: 12 }}>{JSON.stringify(r.detail).slice(0, 140)}</code>
                      ) : (
                        "—"
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