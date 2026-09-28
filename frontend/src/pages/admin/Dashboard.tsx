import { useEffect, useState } from "react";
import { api, httpError } from "../../api/client";
import type { AnalyticsSummary } from "../../api/types";
import { Alert, Card, PageLoader, StatCard, StatusBadge } from "../../components/ui";
import { PageHeader } from "../../components/Layout";

export default function AdminDashboard() {
  const [data, setData] = useState<AnalyticsSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void load();
    async function load() {
      try {
        const { data: d } = await api.get<AnalyticsSummary>("/admin/analytics/summary");
        setData(d);
      } catch (err) {
        setError(await httpError(err).then((e) => e.message));
      }
    }
  }, []);

  if (!data) {
    return error ? <Alert tone="error">{error}</Alert> : <PageLoader />;
  }

  const maxFunnel = Math.max(...data.overall_funnel.map((f) => f.count), 1);

  return (
    <div>
      <PageHeader title="Placement Dashboard" />
      <div className="stat-grid">
        <StatCard label="Students" value={data.total_students} />
        <StatCard label="Drives" value={data.total_drives} sub={`${data.published_drives} published`} />
        <StatCard label="Applications" value={data.total_applications} sub={`${data.unique_applicants} applicants`} />
        <StatCard label="Apps / drive" value={data.applications_per_drive.toFixed(2)} />
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18 }} className="mb-block">
        <div>
          <Card title="Application funnel">
            {data.overall_funnel.length === 0 ? (
              <p className="muted mb-0">No application data yet.</p>
            ) : (
              <div className="stack">
                {data.overall_funnel.map((f) => (
                  <div key={f.label}>
                    <div className="flex-between">
                      <span>{f.label}</span>
                      <strong>{f.count}</strong>
                    </div>
                    <div className="bar">
                      <div className="bar-fill" style={{ width: `${(f.count / maxFunnel) * 100}%` }} />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card title="Status distribution">
            {data.status_stats.length === 0 ? (
              <p className="muted mb-0">No applications yet.</p>
            ) : (
              <div className="stack">
                {data.status_stats.map((s) => (
                  <div className="flex-between" key={s.status}>
                    <StatusBadge status={s.status} />
                    <strong>{s.count}</strong>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>

        <div>
          <Card title="Top drives">
            {data.top_drives.length === 0 ? (
              <p className="muted mb-0">No drives yet.</p>
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Drive</th>
                      <th>Apps</th>
                      <th>Shortlisted</th>
                      <th>Offered</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.top_drives.map((d) => (
                      <tr key={d.drive_id}>
                        <td>
                          <strong>{d.drive_title}</strong>
                          <div className="muted">{d.company_name}</div>
                        </td>
                        <td>{d.apps_total}</td>
                        <td>{d.apps_shortlisted}</td>
                        <td>{d.apps_offered}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>

          <Card title="Department activity">
            {data.department_stats.length === 0 ? (
              <p className="muted mb-0">No data.</p>
            ) : (
              <div className="table-wrap">
                <table className="table">
                  <thead>
                    <tr>
                      <th>Department</th>
                      <th>Students</th>
                      <th>Applications</th>
                      <th>Placed</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.department_stats.map((d) => (
                      <tr key={d.department_code}>
                        <td>
                          {d.department_name}
                          <div className="muted">{d.department_code}</div>
                        </td>
                        <td>{d.students}</td>
                        <td>{d.applications}</td>
                        <td>{d.placed}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}