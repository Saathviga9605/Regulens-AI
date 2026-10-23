import { useState, type FormEvent } from "react";

import { useAuth } from "../app/AuthContext";
import { entries, formatDateTime } from "../app/labels";
import { useApiQuery } from "../app/useApiQuery";
import { useToast } from "../components/Toast";
import {
  Alert,
  Badge,
  Card,
  ConfirmDialog,
  ErrorState,
  LoadingState,
  PageHeader,
  PasswordField,
  SelectField,
  TABLE,
  TextField,
  buttonStyles,
} from "../components/ui";
import { ApiError, apiClient } from "../services/apiClient";
import type { User, UserRole } from "../types/api";

const ROLES: Record<UserRole, string> = { reviewer: "Reviewer", admin: "Administrator" };
const EMPTY_FORM = { username: "", display_name: "", role: "reviewer" as UserRole, password: "" };

/** A change awaiting explicit confirmation. Nothing is sent until the admin confirms. */
type Pending =
  | { kind: "role"; user: User; role: UserRole }
  | { kind: "active"; user: User; active: boolean };

export function UsersPage() {
  const { user: me } = useAuth();
  const toast = useToast();
  const users = useApiQuery(() => apiClient.listUsers(), "users");
  const [message, setMessage] = useState<{ tone: "success" | "error"; text: string } | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [creating, setCreating] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [applying, setApplying] = useState(false);
  const [pendingError, setPendingError] = useState<string | null>(null);

  async function applyPending() {
    if (!pending || applying) return;
    setApplying(true);
    setPendingError(null);
    try {
      const change = pending.kind === "role" ? { role: pending.role } : { is_active: pending.active };
      const updated = await apiClient.updateUser(pending.user.id, change);
      const text = pending.kind === "role"
        ? `Role updated: ${updated.username} is now ${ROLES[updated.role]}.`
        : `${updated.is_active ? "Reactivated" : "Deactivated"}: ${updated.username}.`;
      setMessage({ tone: "success", text });
      toast(text);
      setPending(null);
      users.reload();
    } catch (err) {
      setPendingError(err instanceof ApiError ? err.message : "Request failed. Please try again.");
    } finally {
      setApplying(false);
    }
  }

  async function create(e: FormEvent) {
    e.preventDefault();
    if (creating) return;
    const found: Record<string, string> = {};
    if (!/^[a-zA-Z0-9._-]{3,60}$/.test(form.username)) found.username = "3–60 letters, digits, dots, dashes or underscores.";
    if (form.display_name.trim().length < 2) found.display_name = "Enter a display name.";
    if (form.password.length < 10) found.password = "At least 10 characters.";
    setErrors(found);
    if (Object.keys(found).length) return;
    setCreating(true);
    setMessage(null);
    try {
      const created = await apiClient.createUser(form);
      setMessage({ tone: "success", text: `Created: ${created.username}.` });
      toast(`Created user ${created.username}.`);
      setForm(EMPTY_FORM);
      users.reload();
    } catch (err) {
      // Keep the typed values so the admin can correct and resubmit.
      if (err instanceof ApiError) setErrors(err.fieldErrors);
      setMessage({ tone: "error", text: err instanceof ApiError ? err.message : "Request failed." });
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader eyebrow="Administration" title="Users and roles"
        breadcrumbs={[{ label: "Overview", to: "/" }, { label: "Users" }]}
        description="Reviewer: review applications, act on findings, request evidence, generate reports. Administrator: also manages users, scrutiny rules and the audit trail." />
      {message && <Alert tone={message.tone}>{message.text}</Alert>}

      <ConfirmDialog open={pending !== null} busy={applying} error={pendingError}
        destructive={pending?.kind === "active" && !pending.active}
        title={pending?.kind === "role" ? "Change role?" : pending?.kind === "active" && !pending.active ? "Deactivate user?" : "Reactivate user?"}
        confirmLabel={pending?.kind === "role" ? "Change role" : pending?.kind === "active" && !pending.active ? "Deactivate" : "Reactivate"}
        onConfirm={applyPending} onCancel={() => { setPending(null); setPendingError(null); }}>
        {pending?.kind === "role" && (
          <p>Change <strong>{pending.user.username}</strong> from {ROLES[pending.user.role]} to <strong>{ROLES[pending.role]}</strong>?
            Their active sessions are signed out and the change is recorded in the audit trail.</p>
        )}
        {pending?.kind === "active" && (
          <p>{pending.active ? "Reactivate" : "Deactivate"} <strong>{pending.user.username}</strong>?
            {pending.active ? " They will be able to sign in again." : " They are signed out immediately and cannot sign in until reactivated."}
            {" "}The change is recorded in the audit trail.</p>
        )}
      </ConfirmDialog>

      <Card title="Accounts">
        {users.loading && !users.data ? <LoadingState label="Loading users…" /> : users.error ? (
          <ErrorState message={users.error} onRetry={users.reload} />
        ) : (
          <div className={TABLE.wrap}>
            <table className={`${TABLE.table} min-w-[40rem]`}>
              <caption className="sr-only">Users</caption>
              <thead>
                <tr>
                  <th scope="col" className={TABLE.th}>User</th>
                  <th scope="col" className={TABLE.th}>Role</th>
                  <th scope="col" className={TABLE.th}>Status</th>
                  <th scope="col" className={TABLE.th}>Created</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {(users.data ?? []).map((u) => {
                  const self = u.id === me?.id;
                  return (
                    <tr key={u.id}>
                      <td className={TABLE.td}>
                        <div className="font-medium">{u.display_name}{self && <span className="ml-2"><Badge tone="info">You</Badge></span>}</div>
                        <div className="text-xs text-ink-subtle">{u.username}</div>
                      </td>
                      <td className={TABLE.td}>
                        <label className="sr-only" htmlFor={`role-${u.id}`}>Role for {u.username}</label>
                        <select id={`role-${u.id}`} value={u.role} disabled={self || applying}
                          title={self ? "You cannot change your own role" : undefined}
                          onChange={(e) => setPending({ kind: "role", user: u, role: e.target.value as UserRole })}
                          className="rounded-control border border-line-strong bg-surface px-2 py-1 text-sm">
                          {entries(ROLES).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                        </select>
                      </td>
                      <td className={TABLE.td}>
                        <label className="inline-flex items-center gap-2 text-sm">
                          <input type="checkbox" checked={u.is_active} disabled={self || applying} aria-label={`Active: ${u.username}`}
                            onChange={(e) => setPending({ kind: "active", user: u, active: e.target.checked })} className="h-4 w-4" />
                          <span aria-hidden="true">{u.is_active ? "Active" : "Inactive"}</span>
                        </label>
                      </td>
                      <td className={`${TABLE.td} text-xs`}>{formatDateTime(u.created_at)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card title="Create user" description="Passwords are stored as salted hashes and are never shown again.">
        <form noValidate onSubmit={create} className="grid gap-3 sm:grid-cols-2" aria-label="Create user">
          <TextField label="Username" required value={form.username} error={errors.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
          <TextField label="Display name" required value={form.display_name} error={errors.display_name} onChange={(e) => setForm({ ...form, display_name: e.target.value })} />
          <SelectField label="Role" value={form.role} options={entries(ROLES)} onChange={(e) => setForm({ ...form, role: e.target.value as UserRole })} />
          <PasswordField label="Initial password" required autoComplete="new-password" value={form.password} error={errors.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })} />
          <div className="sm:col-span-2">
            <button type="submit" className={buttonStyles.primary} disabled={creating}>{creating ? "Creating…" : "Create user"}</button>
          </div>
        </form>
      </Card>
    </div>
  );
}
