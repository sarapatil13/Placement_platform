import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, httpError } from "../../api/client";
import type { PaginatedNotifications } from "../../api/types";
import { Button, Card, EmptyState, PageLoader, Tag } from "../../components/ui";
import { PageHeader } from "../../components/Layout";

export default function Notifications() {
  const [data, setData] = useState<PaginatedNotifications | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      const { data: d } = await api.get<PaginatedNotifications>("/notifications", { params: { limit: 50 } });
      setData(d);
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function markAllRead() {
    setBusy(true);
    try {
      await api.post("/notifications/mark-read", { ids: null });
      await load();
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <PageLoader />;

  const items = data?.items ?? [];
  const unread = data?.unread_count ?? 0;

  return (
    <div>
      <PageHeader
        title="Notifications"
        actions={
          unread > 0 ? (
            <Button variant="secondary" className="btn-sm" onClick={markAllRead} disabled={busy}>
              Mark all read ({unread})
            </Button>
          ) : undefined
        }
      />
      {error ? <div className="alert alert-error">{error}</div> : null}
      {items.length === 0 ? (
        <EmptyState message="No notifications yet." />
      ) : (
        items.map((n) => (
          <Card key={n.id} className={n.is_read ? undefined : "unread"}>
            <div className="flex-between">
              <div>
                <strong>{n.title}</strong>
                {!n.is_read ? <Tag tone="info">new</Tag> : null}
                <div className="muted">{new Date(n.created_at).toLocaleString()}</div>
              </div>
            </div>
            <p className="mb-0" style={{ marginTop: 4 }}>
              {n.body}
            </p>
            {n.link ? (
              <div style={{ marginTop: 8 }}>
                <Link to={n.link}>Open →</Link>
              </div>
            ) : null}
          </Card>
        ))
      )}
    </div>
  );
}