import { FormEvent, useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth, extractErrorMessage } from "../auth/AuthContext";
import { Alert, Button, Field, Input } from "../components/ui";

export default function Login() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) {
    return <Navigate to="/app" replace />;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(email, password);
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from ?? "/app", { replace: true });
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login-wrap">
      <div className="login-card">
        <div className="login-brand">
          <span className="brand-mark">PP</span>
          <h1>Placement Platform</h1>
          <p className="muted mb-0">Sign in with your placement-cell account</p>
        </div>
        {error ? <Alert tone="error">{error}</Alert> : null}
        <form onSubmit={handleSubmit}>
          <Field label="Email">
            <Input
              type="email"
              required
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.edu"
            />
          </Field>
          <Field label="Password">
            <Input
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
          <Button type="submit" disabled={busy || !!user} className="btn-block">
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>
        <p className="rule-note" style={{ marginTop: 14 }}>
          Demo accounts are created by <code>python -m app.seed</code>, which prints the
          generated admin and student passwords. Set SEED_ADMIN_PASSWORD and
          SEED_STUDENT_PASSWORD in <code>.env</code> to pin them.
        </p>
      </div>
    </div>
  );
}