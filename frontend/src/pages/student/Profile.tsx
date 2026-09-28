import { FormEvent, useEffect, useState } from "react";
import { api, httpError } from "../../api/client";
import type { SkillRead, StudentDetail } from "../../api/types";
import { Alert, Button, Card, Field, Input, PageLoader, Textarea } from "../../components/ui";
import { PageHeader } from "../../components/Layout";

interface StudentForm {
  phone: string;
  profile_headline: string;
  about: string;
  portfolio_url: string;
  linkedin_url: string;
  github_url: string;
  location: string;
}

const EMPTY: StudentForm = {
  phone: "",
  profile_headline: "",
  about: "",
  portfolio_url: "",
  linkedin_url: "",
  github_url: "",
  location: "",
};

export default function Profile() {
  const [student, setStudent] = useState<StudentDetail | null>(null);
  const [skills, setSkills] = useState<SkillRead[]>([]);
  const [form, setForm] = useState<StudentForm>(EMPTY);
  const [skillsText, setSkillsText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [busy, setBusy] = useState<"profile" | "skills" | null>(null);

  useEffect(() => {
    void load();
    async function load() {
      try {
        const [p, s] = await Promise.all([
          api.get<StudentDetail>("/students/me"),
          api.get<SkillRead[]>("/students/me/skills"),
        ]);
        setStudent(p.data);
        setSkills(s.data);
        setForm({
          phone: p.data.phone ?? "",
          profile_headline: p.data.profile_headline ?? "",
          about: p.data.about ?? "",
          portfolio_url: p.data.portfolio_url ?? "",
          linkedin_url: p.data.linkedin_url ?? "",
          github_url: p.data.github_url ?? "",
          location: p.data.location ?? "",
        });
        setSkillsText(s.data.map((x) => x.name).join(", "));
      } catch (err) {
        setError(await httpError(err).then((e) => e.message));
      }
    }
  }, []);

  function update<K extends keyof StudentForm>(key: K, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function saveProfile(e: FormEvent) {
    e.preventDefault();
    setBusy("profile");
    setError(null);
    setSuccess(null);
    try {
      const { data } = await api.patch<StudentDetail>("/students/me", form);
      setStudent(data);
      setSuccess("Profile updated.");
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(null);
    }
  }

  async function saveSkills() {
    setBusy("skills");
    setError(null);
    setSuccess(null);
    try {
      const names = skillsText
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
        .slice(0, 50);
      const { data } = await api.put<SkillRead[]>("/students/me/skills", { skills: names });
      setSkills(data);
      setSkillsText(data.map((x) => x.name).join(", "));
      setSuccess("Skills updated.");
    } catch (err) {
      setError(await httpError(err).then((e) => e.message));
    } finally {
      setBusy(null);
    }
  }

  if (!student) {
    return error ? <Alert tone="error">{error}</Alert> : <PageLoader />;
  }

  return (
    <div>
      <PageHeader title="My Profile" />
      {error ? <Alert tone="error">{error}</Alert> : null}
      {success ? <Alert tone="success">{success}</Alert> : null}

      <Card title="Academic record (institution-managed)">
        <div className="kv">
          <dt>College ID</dt>
          <dd>{student.college_id}</dd>
          <dt>Department</dt>
          <dd>{student.department_name} ({student.department_code})</dd>
          <dt>Batch</dt>
          <dd>{student.batch_year}</dd>
          <dt>CGPA</dt>
          <dd>{student.cgpa ?? "—"}</dd>
          <dt>Backlogs</dt>
          <dd>{student.backlog_count ?? "—"} (active: {student.active_backlogs ?? "—"})</dd>
          <dt>Gender</dt>
          <dd>{student.gender ?? "—"}</dd>
          <dt>Data verified</dt>
          <dd>{student.academic_data_verified ? "Yes" : "No"}</dd>
        </div>
        <p className="rule-note mb-0">Ask the placement cell to correct any of these fields.</p>
      </Card>

      <Card title="Skills">
        <Field label="Skills (comma separated)">
          <Input value={skillsText} onChange={(e) => setSkillsText(e.target.value)} placeholder="Python, SQL, Data Structures" />
        </Field>
        <div className="skill-chips">
          {skills.map((s) => (
            <span className="tag tag-info" key={s.id}>
              {s.name}
              {s.is_verified ? " ✓" : ""}
            </span>
          ))}
        </div>
        <Button onClick={saveSkills} disabled={busy === "skills"}>
          {busy === "skills" ? "Saving…" : "Save skills"}
        </Button>
      </Card>

      <Card title="Contact & headline">
        <form onSubmit={saveProfile}>
          <div className="form-grid">
            <Field label="Phone">
              <Input value={form.phone} onChange={(e) => update("phone", e.target.value)} />
            </Field>
            <Field label="Location">
              <Input value={form.location} onChange={(e) => update("location", e.target.value)} />
            </Field>
            <Field label="Profile headline">
              <Input value={form.profile_headline} onChange={(e) => update("profile_headline", e.target.value)} maxLength={200} />
            </Field>
            <Field label="Portfolio URL">
              <Input value={form.portfolio_url} onChange={(e) => update("portfolio_url", e.target.value)} />
            </Field>
            <Field label="LinkedIn URL">
              <Input value={form.linkedin_url} onChange={(e) => update("linkedin_url", e.target.value)} />
            </Field>
            <Field label="GitHub URL">
              <Input value={form.github_url} onChange={(e) => update("github_url", e.target.value)} />
            </Field>
          </div>
          <Field label="About">
            <Textarea value={form.about} onChange={(e) => update("about", e.target.value)} maxLength={4000} />
          </Field>
          <Button type="submit" disabled={busy === "profile"}>
            {busy === "profile" ? "Saving…" : "Save profile"}
          </Button>
        </form>
      </Card>
    </div>
  );
}