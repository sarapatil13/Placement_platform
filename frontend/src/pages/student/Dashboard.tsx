import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, httpError } from "../../api/client";
import type { PaginatedDrives } from "../../api/types";
import { Alert, Badge, Button, EmptyState, PageLoader, StatusBadge, Tag } from "../../components/ui";
import { PageHeader } from "../../components/Layout";

export default function Dashboard() {
  const [data, setData] = useState<PaginatedDrives | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void load();
    async function load() {
      try {
        setLoading(true);
        const { data: d } = await api.get<PaginatedDrives>("/drives", { params: { limit: 50 } });
        setData(d);
      } catch (err) {
        setError(await httpError(err).then((e) => e.message));
      } finally {
        setLoading(false);
      }
    }
  }, []);

  if (loading) return <PageLoader />;

  return (
    <div>
      <PageHeader title="Open Drives" actions={<Link to="/app/applications"><Button variant="secondary" className="btn-sm">My applications</Button></Link>} />
      {error ? <Alert tone="error">{error}</Alert> : null}
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
                {d.required_skills.length > 6 ? <Tag tone="neutral">+{d.required_skills.length - 6}</Tag> : null}
              </div>
              <div className="flex-between">
                <span className="muted">Apply by {d.apply_by ? new Date(d.apply_by).toLocaleDateString() : "—"}</span>
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