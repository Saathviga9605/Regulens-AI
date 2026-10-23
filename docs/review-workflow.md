# Reviewer Workflow: Review States, Evidence Requests, Alerts, Reports, Copilot

ReguLens never approves or rejects an application. Review states are a reviewer's assessment of a system finding.

## Review queue
`GET /api/v1/review-queue` summarises each application from its **latest** scrutiny run: unresolved findings by
severity (unresolved = not dismissed/resolved; info-level anomaly indicators excluded), open and overdue evidence
requests, and a review state: `no_scrutiny`, `not_started`, `in_progress`, `complete` (no unresolved findings).
Filters: search, application status, scrutiny status, unresolved severity, unresolved only, review state; sorts:
priority (default: most unresolved high → medium → low, overdue requests, total, ID), application ID, updated.
Counts are computed in Python over all applications — fine for the prototype, not for large volumes.

## Finding review states
| From \ action | confirm | dismiss* | escalate* | request_evidence* | resolve* | reopen* |
|---|---|---|---|---|---|---|
| not_reviewed | confirmed | dismissed | escalated | awaiting_evidence | — | — |
| confirmed | — | dismissed | escalated | awaiting_evidence | resolved | — |
| escalated | confirmed | dismissed | — | awaiting_evidence | resolved | — |
| awaiting_evidence | confirmed | dismissed | escalated | awaiting_evidence | resolved | — |
| dismissed / resolved | — | — | — | — | — | not_reviewed |

`note` (add observation) is allowed in any state and does not change it. `*` = a reason of ≥ 10 characters is
required. Invalid transitions → 409 `invalid_review_transition` (with `allowed_actions`); each request carries
`expected_version`, and a mismatch → 409 `stale_review` (no silent overwrite). Only findings of the latest run can be
acted on (409 `finding_superseded`). Actions append to `finding_review_actions` (actor, previous/new state, note,
optional document/page references) and never change the system outcome, explanation or evidence. When scrutiny is
rerun, the review state of findings with the same `finding_key` is **carried forward** with a `carried_forward`
history entry by `system`.

## Evidence requests
Create from the Evidence requests panel or with the `request_evidence` finding action (which links the finding).
States: `open` → `fulfilled` (requires ≥ 1 linked document) or `cancelled` (reason ≥ 10 chars); `overdue` is an
open request past its due date. Documents are linked **only explicitly**: choose the request in the upload form
(`evidence_request_id` form field) or "Link uploaded document". Uploading never satisfies other requests. Fulfil/
cancel use `expected_version`. No email/SMS is sent.

## Alerts
Generated in the same transaction as these backend events; each has a deterministic dedup key, so reruns and
refreshes never duplicate:
| Event | Dedup key |
|---|---|
| New high-severity issue finding (unresolved) | application + finding_key (once per finding across runs) |
| Scrutiny completed with issues | run id |
| Evidence requested | request id |
| Evidence due within 2 days / overdue (evaluated when alerts are listed) | request id |
| Evidence linked to a request | request + document |
| Finding escalated | review action id |
| Document processing failed | document + checksum + pipeline version |
All staff see all alerts; read state is per user (`alert_reads`). In-app only.

## Preliminary report
`GET /api/v1/applications/{code}/scrutiny-runs/{run_id}/report.pdf` (authenticated; completed runs only) builds a PDF
with PyMuPDF from persisted data: the label "PRELIMINARY SCRUTINY — HUMAN REVIEW REQUIRED", fictional-data notice,
application/institution, run id and rule-set version, summary counts, document inventory and processing status,
findings with severity, outcome, human review state, evidence quotes with document and page, reviewer actions,
simulated issuer results (labelled), evidence requests, limitations/inconclusive results and a disclaimer. All text
is HTML-escaped; content flows over multiple pages; filename `ReguLens-preliminary-scrutiny-<code>-run<n>.pdf`.
Generation is audited. Limitation: the built-in fonts cover Latin text; other scripts may not render.

## Reviewer copilot (no AI model)
`POST /api/v1/applications/{code}/copilot {question, finding_id?}`. Deterministic: keyword intent matching →
retrieval from **this application's** latest-run findings and evaluations, current extracted fields (re-checked
against page text), review actions, evidence requests and simulated checks → fixed answer templates with numbered
sources (finding, document, page, quote). Intents: summary, explain finding (by finding id, rule id, title words or
"highest"), missing/inconclusive, unresolved, evidence requests, compare a field across documents, simulated issuer
status, next steps. It refuses decisions (approve/reject/fraud/authenticity), questions naming another application,
and regulatory-requirement questions (no verified sources exist); unknown questions get help text with nothing
looked up. Document text only ever appears as quoted, labelled data — it is never interpreted, so instructions
embedded in documents have no effect. Only intent and counts are audited (not the question text).
