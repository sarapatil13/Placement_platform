import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, httpError } from "../../api/client";
import type { ApplicationDetail, ApplicationRead } from "../../api/types";
import { Card, EmptyState, PageLoader, StatusBadge } from "../../components/ui";
import { PageHeader } from "../../components/Layout";

async function fetchWithDetail(app: ApplicationRead): Promise<ApplicationDetail> {
  const { data } = await api.get<ApplicationDetail>(`/applications/${app.id}`);
  return data;
}

export default function Applications() {
  const [apps, setApps] = useState<ApplicationDetail[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void load();
    async function load() {
      try {
        const { data } = await api.get<ApplicationRead[]>("/applications/me");
        const details = await Promise.all(data.map((a) => fetchWithDetail(a).catch(() => undefined)));
        setApps(details.filter((d): d is ApplicationDetail => !!d));
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
      <PageHeader title="My Applications" />
      {error ? <AlertInline msg={error} /> : null}
      {!apps || apps.length === 0 ? (
        <EmptyState message="You have not applied to any drives yet." />
      ) : (
        apps.map((a) => (
          <Card key={a.id} title={a.drive_title}>
            <div className="kv">
              <dt>Company</dt>
              <dd>{a.company_name}</dd>
              <dt>Status</dt>
              <dd>
                <StatusBadge status={a.status} />
              </dd>
              <dt>Applied</dt>
              <dd>{new Date(a.applied_at).toLocaleString()}</dd>
              <dt>Updated</dt>
              <dd>{new Date(a.updated_at).toLocaleString()}</dd>
              <dt>Resume</dt>
              <dd>{a.resume_filename ?? "—"}</dd>
              <dt>Cover note</dt>
              <dd>{a.cover_note ?? "—"}</dd>
            </div>
            {a.status_history.length > 0 ? (
              <div className="timeline" style={{ marginTop: 14 }}>
                {a.status_history.map((h) => (
                  <div className="timeline-item" key={h.id}>
                    <div className="row">
                      <StatusBadge status={h.to_status} />
                      <span className="muted">{new Date(h.created_at).toLocaleString()}</span>
                    </div>
                    {h.note ? <div className="muted">{h.note}</div> : null}
                  </div>
                ))}
              </div>
            ) : null}
            <div style={{ marginTop: 12 }}>
              <Link to={`/app/drives/${a.drive_id}`}>View drive →</Link>
            </div>
          </Card>
        ))
      )}
    </div>
  );
}

function AlertInline({ msg }: { msg: string }) {
  return <div className="alert alert-error">{msg}</div>;
}