import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, httpError } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import type { ApplicationRead, DriveEligibilityCheck, DriveRead, DriveRound } from "../../api/types";
import { Alert, Badge, Button, Card, PageLoader, Select, Tag } from "../../components/ui";
import { PageHeader } from "../../components/Layout";
import { ROUND_TYPE_LABELS } from "../../components/DriveRoundsEditor";

export default function DriveDetail() {
  const { driveId } = useParams<{ driveId: string }>();
  const { user } = useAuth();
  const [drive, setDrive] = useState<DriveRead | null>(null);
  const [eligibility, setEligibility] = useState<DriveEligibilityCheck | null>(null);
  const [rounds, setRounds] = useState<DriveRound[]>([]);
  const [myApp, setMyApp] = useState<ApplicationRead | null>(null);
  const [resumes, setResumes] = useState<{ id: string; filename: string; is_primary: boolean }[]>([]);
  const [resumeId, setResumeId] = useState("");
  const [coverNote, setCoverNote] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<"eligibility" | "apply" | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const isStudent = user?.role === "student";

  useEffect(() => {
    if (!driveId) return;
    void loadAll();
  }, [driveId]);

  const loadAll = useCallback(async () => {
    if (!driveId) return;
    try {
      const [driveResp, eligResp, appResp, roundsResp] = await Promise.all([
        api.get<DriveRead>(`/drives/${driveId}`),
        api.get<DriveEligibilityCheck>(`/drives/${driveId}/eligibility`),
        api.get<ApplicationRead[]>(`/applications/drive/${driveId}`),
        api.get<DriveRound[]>(`/drives/${driveId}/rounds`),
      ]);
      setDrive(driveResp.data);
      setEligibility(eligResp.data);
      setMyApp(appResp.data[0] ?? null);
      setRounds(roundsResp.data);
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    }
    if (isStudent) {
      try {
        const r = await api.get<{ id: string; filename: string; is_primary: boolean }[]>("/resumes");
        setResumes(r.data);
        const primary = r.data.find((x) => x.is_primary) ?? r.data[0];
        if (primary) setResumeId(primary.id);
      } catch {
        /* resumes optional */
      }
    }
  }, [driveId, isStudent]);

  async function runEligibility() {
    setBusy("eligibility");
    setError(null);
    try {
      const { data } = await api.get<DriveEligibilityCheck>(`/drives/${driveId}/eligibility`);
      setEligibility(data);
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(null);
    }
  }

  async function submitApplication() {
    if (!driveId) return;
    setBusy("apply");
    setError(null);
    setSuccess(null);
    try {
      const { data } = await api.post<ApplicationRead>("/applications", {
        drive_id: driveId,
        resume_id: resumeId || null,
        cover_note: coverNote || null,
      });
      setMyApp(data);
      setSuccess("Application submitted.");
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(null);
    }
  }

  async function withdrawApplication() {
    if (!driveId || !myApp) return;
    try {
      const { data } = await api.post<ApplicationRead>(`/applications/${myApp.id}/withdraw`, {});
      setMyApp(data);
      setSuccess("Application withdrawn.");
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    }
  }

  if (!drive) {
    return error ? (
      <div>
        <Alert tone="error">{error}</Alert>
        <Link to="/app">Back to drives</Link>
      </div>
    ) : (
      <PageLoader />
    );
  }

  const alreadyApplied = !!myApp && myApp.status !== "withdrawn";

  return (
    <div>
      <PageHeader title={drive.title} actions={<Link to="/app"><Button variant="secondary" className="btn-sm">← Back</Button></Link>} />
      {error ? <Alert tone="error">{error}</Alert> : null}
      {success ? <Alert tone="success">{success}</Alert> : null}

      <Card title="Overview">
        <dl className="kv" style={{ display: "grid", gridTemplateColumns: "140px 1fr", gap: "6px 14px" }}>
          <dt>Company</dt>
          <dd>{drive.company_name}</dd>
          <dt>Role</dt>
          <dd>{drive.role_title}</dd>
          <dt>Employment</dt>
          <dd>{drive.employment_type.replace("_", " ")}</dd>
          <dt>Location</dt>
          <dd>{drive.location ?? "—"}</dd>
          <dt>CTC</dt>
          <dd>{drive.ctc_lpa ? `${drive.ctc_lpa} LPA` : "—"}</dd>
          <dt>Stipend</dt>
          <dd>{drive.stipend ? `₹${drive.stipend}` : "—"}</dd>
          <dt>Apply by</dt>
          <dd>{drive.apply_by ? new Date(drive.apply_by).toLocaleString() : "—"}</dd>
          <dt>Drive date</dt>
          <dd>{drive.drive_date ? new Date(drive.drive_date).toLocaleString() : "—"}</dd>
        </dl>
        {drive.description ? <p>{drive.description}</p> : null}
        <div className="skill-chips" style={{ marginTop: 10 }}>
          {drive.required_skills.map((s) => (
            <Tag key={s}>{s}</Tag>
          ))}
        </div>
      </Card>

      {rounds.length > 0 ? (
        <Card title="Interview process">
          <ol className="mb-0" style={{ paddingLeft: 18 }}>
            {rounds.map((r) => (
              <li key={r.id} style={{ marginBottom: 10 }}>
                <strong>{r.title || ROUND_TYPE_LABELS[r.round_type]}</strong>{" "}
                <Tag tone="neutral">{ROUND_TYPE_LABELS[r.round_type]}</Tag>
                {r.scheduled_at ? (
                  <span className="muted"> · {new Date(r.scheduled_at).toLocaleString()}</span>
                ) : null}
                {r.topics.length > 0 ? (
                  <div className="skill-chips" style={{ marginTop: 4 }}>
                    {r.topics.map((t) => (
                      <Tag key={t}>{t}</Tag>
                    ))}
                  </div>
                ) : null}
              </li>
            ))}
          </ol>
        </Card>
      ) : null}

      <Card title="Eligibility">
        {eligibility ? (
          <div className="stack">
            <div className="row">
              <Badge tone={eligibility.eligible ? "good" : "bad"}>
                {eligibility.eligible ? "Eligible" : "Not eligible"} · score {eligibility.score}
              </Badge>
              {drive.criteria.length === 0 ? <Badge tone="warn">No criteria configured</Badge> : null}
              {!drive.eligibility_confirmed ? <Badge tone="warn">Pending confirmation</Badge> : null}
            </div>
            <p className="mb-0">{eligibility.reason}</p>
            {eligibility.passed_rules.length > 0 ? (
              <div>
                <strong>Passed:</strong>
                <ul className="mb-0">
                  {eligibility.passed_rules.map((r, i) => (
                    <li key={i}>{String(r.detail ?? r.criterion_type ?? "")}</li>
                  ))}
                </ul>
              </div>
            ) : null}
            {eligibility.failed_rules.length > 0 ? (
              <div>
                <strong>Not met:</strong>
                <ul>
                  {eligibility.failed_rules.map((r, i) => (
                    <li key={i}>{String(r.detail ?? r.reason ?? r.criterion_type ?? "")}</li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        ) : (
          <p className="muted">Check your eligibility for this drive.</p>
        )}
        <div style={{ marginTop: 12 }}>
          <Button variant="secondary" className="btn-sm" onClick={runEligibility} disabled={busy === "eligibility"}>
            {busy === "eligibility" ? "Checking…" : "Check eligibility"}
          </Button>
        </div>
      </Card>

      {isStudent ? (
        <Card title="Apply">
          {alreadyApplied ? (
            <div className="stack">
              <div className="row">
                <Badge>Current status</Badge>
                <Badge tone={drive.status === "published" ? "good" : "warn"}>{myApp!.status}</Badge>
                <Badge tone="info">Applied {new Date(myApp!.applied_at).toLocaleString()}</Badge>
              </div>
              {myApp!.status === "withdrawn" ? (
                <Button variant="secondary" onClick={submitApplication} disabled={busy === "apply"}>
                  Re-apply
                </Button>
              ) : null}
              {!["withdrawn", "rejected", "offer_accepted", "offer_declined"].includes(myApp!.status) ? (
                <Button variant="danger" className="btn-sm" onClick={withdrawApplication}>
                  Withdraw application
                </Button>
              ) : null}
            </div>
          ) : (
            <div>
              {resumes.length === 0 ? (
                <Alert tone="warn">
                  You have no resumes on file.{" "}
                  <Link to="/app/resumes">Upload one</Link> before applying.
                </Alert>
              ) : (
                <div style={{ maxWidth: 420 }}>
                  <label className="field">
                    <span className="field-label">Resume</span>
                    <Select value={resumeId} onChange={(e) => setResumeId(e.target.value)}>
                      {resumes.map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.filename}
                          {r.is_primary ? " (primary)" : ""}
                        </option>
                      ))}
                    </Select>
                  </label>
                </div>
              )}
              <label className="field" style={{ maxWidth: 520 }}>
                <span className="field-label">Cover note (optional)</span>
                <textarea
                  className="input"
                  maxLength={2000}
                  value={coverNote}
                  onChange={(e) => setCoverNote(e.target.value)}
                  placeholder="A short note for the recruiter (max 2000 chars)"
                />
              </label>
              <Button onClick={submitApplication} disabled={busy === "apply"}>
                {busy === "apply" ? "Submitting…" : "Apply now"}
              </Button>
            </div>
          )}
        </Card>
      ) : (
        <Card title="Administration">
          <Alert tone="info">
            Manage this drive from the{" "}
            <Link to={`/app/admin/drives/${drive.id}`}>admin drive view</Link>.
          </Alert>
        </Card>
      )}

      {myApp?.status === "withdrawn" ? (
        <Card title="Withdrawn">
          <p className="mb-0 muted">
            {myApp.withdrawn_reason ?? "No reason recorded."} You may re-apply above.
          </p>
        </Card>
      ) : null}
    </div>
  );
}