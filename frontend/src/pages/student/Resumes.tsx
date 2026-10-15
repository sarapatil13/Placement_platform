import { useEffect, useState } from "react";
import { api, httpError } from "../../api/client";
import type { DriveRead, PreparationRoadmap, ResumeAnalysisResult, ResumeDetail } from "../../api/types";
import { Alert, Button, Card, EmptyState, PageLoader, Select, Tag } from "../../components/ui";
import { PageHeader } from "../../components/Layout";
import type { ChangeEventHandler, DragEvent } from "react";

export default function Resumes() {
  const [resumes, setResumes] = useState<ResumeDetail[] | null>(null);
  const [drives, setDrives] = useState<DriveRead[]>([]);
  const [analysis, setAnalysis] = useState<ResumeAnalysisResult | null>(null);
  const [roadmap, setRoadmap] = useState<PreparationRoadmap | null>(null);
  const [analysisDrive, setAnalysisDrive] = useState("");
  const [analysisResume, setAnalysisResume] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);

  useEffect(() => {
    void load();
    async function load() {
      try {
        const [r, d] = await Promise.all([
          api.get<ResumeDetail[]>("/resumes"),
          api.get<{ items: DriveRead[] }>("/drives", { params: { limit: 100 } }),
        ]);
        setResumes(r.data);
        setDrives(d.data.items);
        if (r.data.length > 0) setAnalysisResume(r.data[0].id);
        if (d.data.items.length > 0) setAnalysisDrive(d.data.items[0].id);
      } catch (err) {
        setError(await httpError(err).then((e) => e.message));
      }
    }
  }, []);

  const onFileInput: ChangeEventHandler<HTMLInputElement> = async (e) => {
    const file = e.target.files?.[0];
    if (file) void upload(file);
    e.target.value = "";
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files?.[0];
    if (file) void upload(file);
  };

  async function upload(file: File) {
    setBusy("upload");
    setError(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post<{ resume: ResumeDetail; message: string }>("/resumes", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResumes((prev) => (prev ? [data.resume, ...prev] : [data.resume]));
      if (!analysisResume) setAnalysisResume(data.resume.id);
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(null);
    }
  }

  async function setPrimary(id: string) {
    setBusy("primary");
    setError(null);
    try {
      await api.post(`/resumes/${id}/set-primary`, {});
      setResumes((prev) =>
        prev?.map((r) => ({
          ...r,
          is_primary: r.id === id,
        })) ?? null,
      );
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(null);
    }
  }

  async function remove(id: string) {
    setBusy("delete");
    setError(null);
    try {
      await api.delete(`/resumes/${id}`);
      setResumes((prev) => prev?.filter((r) => r.id !== id) ?? null);
      if (analysisResume === id) setAnalysisResume("");
      if (roadmap) setRoadmap(null);
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(null);
    }
  }

  async function runAnalysis() {
    if (!analysisResume || !analysisDrive) return;
    setBusy("analysis");
    setError(null);
    setRoadmap(null);
    try {
      const { data } = await api.post<ResumeAnalysisResult>("/resumes/analyze", {
        resume_id: analysisResume,
        drive_id: analysisDrive,
      });
      setAnalysis(data);
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(null);
    }
  }

  async function runRoadmap() {
    if (!analysisResume || !analysisDrive) return;
    setBusy("roadmap");
    setError(null);
    try {
      const { data } = await api.post<PreparationRoadmap>(`/resumes/${analysisDrive}/roadmap`, {
        resume_id: analysisResume,
      });
      setRoadmap(data);
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(null);
    }
  }

  if (!resumes) {
    return error ? <Alert tone="error">{error}</Alert> : <PageLoader />;
  }

  return (
    <div>
      <PageHeader title="My Resumes" />
      {error ? <Alert tone="error">{error}</Alert> : null}

      <Card title="Upload">
        <div
          className={`empty-state ${dragging ? "dragging" : ""}`}
          style={{ border: "2px dashed var(--border)", borderRadius: 12 }}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          Drag & drop a PDF or DOCX here, or
          <label className="btn btn-secondary btn-sm" style={{ marginLeft: 8 }}>
            browse files
            <input type="file" accept=".pdf,.docx" hidden onChange={onFileInput} />
          </label>
          <p className="rule-note mb-0">Max 10 resumes. Primary resume is used for applications.</p>
        </div>
      </Card>

      {resumes.length === 0 ? (
        <EmptyState message="No resumes uploaded yet." />
      ) : (
        <div>
          {resumes.map((r) => (
            <Card key={r.id}>
              <div className="flex-between">
                <div>
                  <strong>{r.filename}</strong>{" "}
                  {r.is_primary ? <Tag tone="good">primary</Tag> : null}
                  <div className="muted">
                    {(r.size_bytes / 1024).toFixed(1)} KB · parsed:{" "}
                    {r.parse_status === "parsed" ? "yes" : r.parse_status} ·{" "}
                    {new Date(r.created_at).toLocaleDateString()}
                  </div>
                  {r.parsed_skills.length > 0 ? (
                    <div className="skill-chips" style={{ marginTop: 6 }}>
                      {r.parsed_skills.slice(0, 12).map((s) => (
                        <Tag key={s}>{s}</Tag>
                      ))}
                    </div>
                  ) : null}
                </div>
                <div className="row">
                  {!r.is_primary ? (
                    <Button variant="secondary" className="btn-sm" onClick={() => void setPrimary(r.id)} disabled={busy !== null}>
                      Make primary
                    </Button>
                  ) : null}
                  <Button variant="danger" className="btn-sm" onClick={() => void remove(r.id)} disabled={busy !== null}>
                    Delete
                  </Button>
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}

      {resumes.length > 0 && drives.length > 0 ? (
        <Card title="Fit analysis & prep roadmap">
          <div className="row">
            <label className="field mb-0" style={{ minWidth: 260 }}>
              <span className="field-label">Resume</span>
              <Select value={analysisResume} onChange={(e) => setAnalysisResume(e.target.value)}>
                {resumes.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.filename}
                  </option>
                ))}
              </Select>
            </label>
            <label className="field mb-0" style={{ minWidth: 260 }}>
              <span className="field-label">Target drive</span>
              <Select value={analysisDrive} onChange={(e) => setAnalysisDrive(e.target.value)}>
                {drives.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.title}
                  </option>
                ))}
              </Select>
            </label>
          </div>
          <div className="form-actions">
            <Button onClick={runAnalysis} disabled={busy !== null}>
              {busy === "analysis" ? "Analyzing…" : "Analyse fit"}
            </Button>
            <Button variant="secondary" onClick={runRoadmap} disabled={busy !== null}>
              {busy === "roadmap" ? "Building…" : "Build roadmap"}
            </Button>
          </div>
          {analysis ? (
            <div className="stack" style={{ marginTop: 16 }}>
              <div className="row">
                <Tag tone={analysis.skill_match >= 70 ? "good" : analysis.skill_match >= 40 ? "warn" : "bad"}>
                  {analysis.skill_match}% skill match
                </Tag>
              </div>
              <div className="bar" style={{ maxWidth: 420 }}>
                <div className="bar-fill" style={{ width: `${Math.min(analysis.skill_match, 100)}%` }} />
              </div>
              <div className="kv">
                <dt>Matched</dt>
                <dd>{analysis.matched_skills.join(", ") || "—"}</dd>
                <dt>Partial</dt>
                <dd>{analysis.partial_skills.join(", ") || "—"}</dd>
                <dt>Missing</dt>
                <dd>{analysis.missing_skills.join(", ") || "—"}</dd>
              </div>
              {analysis.feedback_text ? <p className="mb-0">{analysis.feedback_text}</p> : null}
            </div>
          ) : null}
          {roadmap ? (
            <div className="stack" style={{ marginTop: 16 }}>
              <strong>Roadmap</strong>
              {roadmap.roadmap_steps.map((s, i) => (
                <div key={i}>{i + 1}. {s}</div>
              ))}
              {roadmap.suggested_practice.length > 0 ? (
                <>
                  <strong>Suggested practice</strong>
                  {roadmap.suggested_practice.map((s, i) => (
                    <div key={i}>• {s}</div>
                  ))}
                </>
              ) : null}
              {roadmap.rounds.length > 0 ? (
                <>
                  <strong>Rounds &amp; focus areas</strong>
                  {roadmap.rounds.map((r) => (
                    <div key={r.round_id}>
                      {r.position}. {r.title}
                      {r.focus_skills.length > 0 ? ` — focus: ${r.focus_skills.join(", ")}` : ""}
                    </div>
                  ))}
                </>
              ) : null}
              <p className="rule-note mb-0">{roadmap.disclaimer}</p>
            </div>
          ) : null}
        </Card>
      ) : null}
    </div>
  );
}