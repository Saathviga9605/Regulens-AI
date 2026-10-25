# Security, Roles and Audit (prototype)

ReguLens is a prototype. Nothing here is a production-grade identity system or a certified audit store.

## Authentication
- Local accounts in `users`; passwords hashed with **scrypt** (stdlib, random 16-byte salt, constant-time compare).
  Minimum length 10. No password is ever logged or audited.
- `POST /api/v1/auth/login` returns an opaque 256-bit bearer token; only its SHA-256 is stored (`auth_sessions`).
  Sessions expire after `REGULENS_SESSION_TTL_MINUTES` (default 480) and are revoked on logout, deactivation,
  role or password change.
- After `REGULENS_LOGIN_MAX_FAILURES` failed attempts for a username within `REGULENS_LOGIN_LOCKOUT_MINUTES`,
  sign-in returns 429. Unknown usernames and wrong passwords get the same message and similar timing.
- The frontend keeps the token in `sessionStorage` (cleared when the tab closes) and sends it as
  `Authorization: Bearer`. Documents and reports are downloaded with that header (no public links).
- Every endpoint except `/health`, `/system/info` and `/auth/login` requires a session (401 `not_authenticated`).
  Roles/user ids are never read from request bodies; request schemas reject unknown fields.

### Demo accounts (LOCAL DEMO ONLY — CHANGE BEFORE SHARING)
`.env.example` and the settings defaults contain **public** local demo credentials (`demo.reviewer` /
`Reviewer@Demo2026`, `demo.admin` / `Admin@Demo2026`), configured by `REGULENS_DEMO_REVIEWER_USERNAME`,
`REGULENS_DEMO_REVIEWER_PASSWORD`, `REGULENS_DEMO_ADMIN_USERNAME`, `REGULENS_DEMO_ADMIN_PASSWORD` and
`REGULENS_DEMO_USERS_ENABLED`. They exist so a fresh checkout can be demonstrated; change them before anyone else
can reach the app.

- `python -m app.cli seed` bootstraps them (and `create-demo-users` does so explicitly) via
  `services/auth.bootstrap_demo_users`. It is idempotent and touches **only** the two configured usernames: missing
  accounts are created; an existing one gets its role and active state reconciled and its password rehashed only if
  the configured password no longer verifies. Any change revokes that account's sessions. Other users are never
  modified, and nothing is deleted.
- Stored as scrypt hashes only. Passwords are never printed by the CLI, logged, written to audit metadata
  (`user.demo_bootstrap` records username, role and created/updated/unchanged), returned by any endpoint or included
  in the frontend bundle. `/system/info` exposes only a boolean `demo_mode`, which drives the "Local demo" badges.
- **Production guard:** with `REGULENS_ENVIRONMENT=production`, demo accounts are switched off, and setting
  `REGULENS_DEMO_USERS_ENABLED=true` explicitly is a startup configuration error. The bootstrap refuses to run in
  production or when disabled, so ordinary production startup never creates demo users.
- The setup never overwrites an existing `.env` (`if (-not (Test-Path .env)) { Copy-Item .env.example .env }`);
  `.env` is git-ignored.
Other users: `python -m app.cli create-user --username NAME --role reviewer|admin` (password from
`REGULENS_NEW_USER_PASSWORD` or a prompt), or the Users page as administrator.

## Roles (enforced on the server)
| Capability | Reviewer | Administrator |
|---|---|---|
| View applications, documents, findings, evidence, alerts, per-application activity | ✓ | ✓ |
| Upload/process documents, run scrutiny, simulated issuer checks | ✓ | ✓ |
| Review actions, evidence requests, reports, copilot | ✓ | ✓ |
| View rules | ✓ | ✓ |
| Create/change rules | — (403) | ✓ |
| Manage users and roles | — (403) | ✓ |
| Global audit log (`/audit-events`) | — (403) | ✓ |

Denied attempts are audited (`authorization.denied`). Administrators cannot demote or deactivate themselves.
**Limitation:** there is no per-application assignment — every reviewer can access every application.

### Cross-case reviewer permission (Deliverable 7)
A per-user `cross_case_reviewer` flag, granted by an administrator (never to themselves) and independent of role,
is required for every case-pair route (pair list/detail, page images, dispositions). Ordinary reviewers receive only
restricted alerts that never name the linked case. Grants/revocations revoke sessions and are audited
(`user.permission_changed`); successful and refused cross-case access is audited with actor, pair id and action and
no document content. See [reuse-detection.md](reuse-detection.md#cross-case-access-control). Limitation: no
per-application assignment exists, so applications themselves remain visible to all reviewers.

## Audit log
`audit_events` is written in the same database transaction as the action it describes (failures/denials are written
separately). Recorded: sign-in/out (success, failure, lockout), application/institution create/edit/status, document
upload/delete/processing, scrutiny runs, rule changes, simulated issuer checks, review actions, evidence-request
lifecycle, report generation, user/role changes, copilot use (intent and counts only — not the question text),
data resets, authorization denials. Each entry: id, UTC timestamp, actor, action, resource, application, outcome,
request id, small structured details (no document text, passwords or tokens).

There is **no update or delete endpoint**. This is an application-level append-only log only: it is not
cryptographically chained, not WORM storage and not legally certified; anyone with direct database access can alter
it. `reset-data` keeps audit rows and records the reset itself.

## Not in scope
SSO/MFA, password reset flows, CSRF tokens (not needed for bearer-header auth), rate limiting beyond login,
encryption at rest, per-application access control, security certification.
