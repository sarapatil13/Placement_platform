import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, httpError } from "../../api/client";
import type { DashboardDriveItem, PaginatedDrives, StudentDashboard } from "../../api/types";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  PageLoader,
  StatCard,
  StatusBadge,
  Tag,
} from "../../components/ui";
import { PageHeader } from "../../components/Layout";

function daysLeftLabel(item: DashboardDriveItem): string {
  if (item.days_left == null) return "No deadline set";
  if (item.days_left < 1) return "Due within 24h";
  return `${item.days_left.toFixed(1)} days left`;
}

export default function Dashboard() {
  const [data, setData] = useState<PaginatedDrives | null>(null);
  const [summary, setSummary] = useState<StudentDashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void load();
    async function load() {
      try {
        setLoading(true);
        const [drives, dashboard] = await Promise.all([
          api.get<PaginatedDrives>("/drives", { params: { limit: 50 } }),
          api.get<StudentDashboard>("/students/me/dashboard"),
        ]);
        setData(drives.data);
        setSummary(dashboard.data);
      } catch (err) {
        setError(await httpError(err).then((e) => e.message));
      } finally {
        setLoading(false);
      }
    }
  }, []);

  if (loading) return <PageLoader />;

  const statusEntries = Object.entries(summary?.application_counts_by_status ?? {});
  const topGap = summary?.top_skill_gaps[0];
  const closingSoon = summary?.closing_soon ?? [];

  return (
    <div>
      <PageHeader
        title="Dashboard"
        actions={
          <Link to="/app/applications">
            <Button variant="secondary" className="btn-sm">
              My applications
            </Button>
          </Link>
        }
      />
      {error ? <Alert tone="error">{error}</Alert> : null}

      {summary ? (
        <>
          <div className="stat-grid">
            <StatCard
              label="Eligible open drives"
              value={summary.eligible_open_drives.length}
              sub="You can apply to these now"
            />
            <StatCard
              label="Closing soon"
              value={summary.closing_soon.length}
              sub="Deadline within 72 hours"
            />
            <StatCard
              label="My applications"
              value={summary.total_applications}
              sub={`${statusEntries.length} status${statusEntries.length === 1 ? "" : "es"}`}
            />
            <StatCard
              label="Top skill gap"
              value={topGap ? topGap.skill : "—"}
              sub={topGap ? `Missing in ${topGap.drives} drive(s)` : "No gaps detected"}
            />
          </div>

          {closingSoon.length > 0 || statusEntries.length > 0 ? (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 14 }}>
              <Card title="Closing soon">
                {closingSoon.length === 0 ? (
                  <p className="muted mb-0">Nothing closing in the next 72 hours.</p>
                ) : (
                  <div className="stack">
                    {closingSoon.map((item) => (
                      <div className="flex-between" key={item.drive_id}>
                        <div>
                          <Link to={`/app/drives/${item.drive_id}`}>
                            <strong>{item.title}</strong>
                          </Link>
                          <div className="muted">{item.company_name}</div>
                        </div>
                        <Badge tone="warn">{daysLeftLabel(item)}</Badge>
                      </div>
                    ))}
                  </div>
                )}
              </Card>

              <Card title="My applications by status">
                {statusEntries.length === 0 ? (
                  <p className="muted mb-0">You have not applied to any drive yet.</p>
                ) : (
                  <div className="stack">
                    {statusEntries.map(([status, count]) => (
                      <div className="flex-between" key={status}>
                        <StatusBadge status={status} />
                        <strong>{count}</strong>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </div>
          ) : null}
        </>
      ) : null}

      <h2 style={{ marginTop: 8, marginBottom: 14 }}>Open Drives</h2>
      {!data || data.items.length === 0 ? (
        <EmptyState message="No drives are currently open for application." />
      ) : (
        <div className="drive-grid">
          {data.items.map((d) => (
            <div className="drive-card" key={d.id}>
              <div className="flex-between">
                <span className="muted">{d.company_name}</span>
                <StatusBadge status={d.status} />
              </div>
              <h3>{d.title}</h3>
              <div className="muted">{d.role_title}</div>
              <div className="row">
                {d.ctc_lpa ? <Badge>{d.ctc_lpa} LPA</Badge> : null}
                {d.employment_type ? <Badge>{d.employment_type.replace("_", " ")}</Badge> : null}
                {d.location ? <Badge>{d.location}</Badge> : null}
              </div>
              {d.criteria.length > 0 ? (
                <div className="rule-note">Eligibility criteria confirmed</div>
              ) : (
                <div className="rule-note">Criteria not yet finalised</div>
              )}
              <div className="skill-chips">
                {d.required_skills.slice(0, 6).map((s) => (
                  <Tag key={s}>{s}</Tag>
                ))}
                {d.required_skills.length > 6 ? (
                  <Tag tone="neutral">+{d.required_skills.length - 6}</Tag>
                ) : null}
              </div>
              <div className="flex-between">
                <span className="muted">
                  Apply by {d.apply_by ? new Date(d.apply_by).toLocaleDateString() : "—"}
                </span>
                <Link to={`/app/drives/${d.id}`}>
                  <Button className="btn-sm">View</Button>
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
