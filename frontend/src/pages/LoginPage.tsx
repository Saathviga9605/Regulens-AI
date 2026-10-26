import { useState, type FormEvent } from "react";
import { Navigate, useLocation, useNavigate } from "react-router";

import { useAuth } from "../app/AuthContext";
import { IDENTITY_STATEMENT } from "../app/navigation";
import { Wordmark } from "../components/BrandMark";
import { Alert, PasswordField, TextField, buttonStyles } from "../components/ui";
import { ApiError } from "../services/apiClient";

export function LoginPage() {
  const { user, login, notice } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const from = (location.state as { from?: string } | null)?.from ?? "/";
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ username?: string; password?: string }>({});
  const [error, setError] = useState<{ title: string; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  if (user) return <Navigate to={from} replace />;

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    const found = { username: username.trim() ? undefined : "Enter your username.", password: password ? undefined : "Enter your password." };
    setErrors(found);
    if (found.username || found.password) {
      setError({ title: "Sign-in details missing", text: "Enter your username and password." });
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await login(username.trim(), password);
      navigate(from, { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.code === "too_many_attempts") {
        setError({ title: "Temporarily locked", text: err.message });
      } else {
        setError({ title: "Sign-in failed", text: err instanceof ApiError ? err.message : "Sign-in failed." });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <div className="h-1.5 bg-saffron-500" aria-hidden="true" />
      <header className="bg-brand-900 px-4 py-3 sm:px-8"><Wordmark inverse /></header>
      <main className="flex flex-1 items-start justify-center px-4 py-10 sm:items-center">
        <div className="grid w-full max-w-4xl overflow-hidden rounded-panel border border-line bg-surface shadow-panel md:grid-cols-2">
          <section aria-labelledby="about-heading" className="hidden bg-brand-50 p-8 md:block">
            <h2 id="about-heading" className="text-lg font-semibold text-brand-900">Preliminary scrutiny workspace</h2>
            <p className="mt-2 text-sm text-ink-muted">
              ReguLens AI helps reviewers organise evidence for Extension of Approval applications: document processing,
              evidence-quoted findings, configurable checks, evidence requests and an audit trail.
            </p>
            <ul className="mt-4 space-y-2 text-sm text-ink">
              <li>• Every finding cites its source document and page.</li>
              <li>• Uncertain results are shown as inconclusive, never as passes.</li>
              <li>• Decisions always remain with authorised human reviewers.</li>
            </ul>
          </section>
          <section aria-labelledby="signin-heading" className="p-6 sm:p-8">
            <h1 id="signin-heading" className="text-xl font-semibold text-brand-900">Sign in to ReguLens AI</h1>
            <p className="mt-1 text-sm text-ink-muted">Use your reviewer or administrator account.</p>
            <div className="mt-4 space-y-3">
              {notice && <Alert tone="info">{notice}</Alert>}
              {error && <Alert tone="error" title={error.title}>{error.text}</Alert>}
              <form noValidate onSubmit={submit} className="space-y-4" aria-label="Sign in">
                <TextField label="Username" autoComplete="username" required value={username} error={errors.username}
                  onChange={(e) => setUsername(e.target.value)} />
                <PasswordField label="Password" autoComplete="current-password" required value={password} error={errors.password}
                  onChange={(e) => setPassword(e.target.value)} />
                <button type="submit" className={`${buttonStyles.primary} w-full`} disabled={busy} aria-busy={busy}>
                  {busy ? "Signing in…" : "Sign in"}
                </button>
              </form>
            </div>
          </section>
        </div>
      </main>
      <footer className="px-4 py-4 text-center text-xs text-ink-subtle">
        {IDENTITY_STATEMENT}
      </footer>
    </div>
  );
}
