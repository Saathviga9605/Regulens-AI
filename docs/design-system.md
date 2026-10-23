# Design System

ReguLens AI uses a restrained public-sector visual language: deep navy and indigo structure, warm off-white
canvas, slate text, muted saffron and teal accents, and semantic red / amber / green / blue for status. It is an
original design. It does not copy any government website, uses no national or government emblem, and must never
imply an official AICTE affiliation. Every screen carries the trust notice:

> Decision-support prototype. Findings require human review. Not an official AICTE decision.

## Tokens (`frontend/src/index.css`)

Tokens are Tailwind v4 `@theme` variables, so each one is also a utility class (`bg-brand-900`, `text-ink-muted`,
`rounded-panel`…). Components use **only** tokens; raw palette classes (`slate-*`, `blue-*`, `red-*`…) are not used.

| Group | Tokens | Use |
|---|---|---|
| Brand | `brand-950 … brand-50` | Header and sidebar (`brand-900`), primary buttons (`brand-800`), links (`brand-700`), tints |
| Accent | `saffron-600/500/100`, `teal-700/100` | Focus ring and active nav (saffron), completed/positive metrics (teal). Accents never carry meaning alone |
| Surfaces | `canvas`, `surface`, `surface-muted`, `line`, `line-strong` | Page background, cards, muted panels, borders |
| Text | `ink`, `ink-muted`, `ink-subtle` | Body, secondary and tertiary text (all ≥ 4.5:1 on `surface`) |
| Semantic | `danger-*`, `warning-*`, `success-*`, `info-*` (`-700/-800`, `-bg`, `-line`) | Errors and high severity, warnings and amber states, success, information |
| Type | `font-sans` (Segoe UI / Noto Sans stack), `font-mono` | UI text; IDs, rule codes and quoted evidence |
| Shape | `radius-control`, `radius-panel`, `shadow-panel`, `shadow-overlay` | Inputs and buttons; cards; dialogs and menus |
| Layout (`:root`) | `--layout-content-max`, `--layout-sidebar`, `--layout-header` | Content width, sidebar width, sticky header height |
| Layers (`:root`) | `--z-sticky`, `--z-drawer`, `--z-dialog`, `--z-toast` | Stacking order |

Breakpoints are Tailwind's defaults (`sm` 640, `md` 768, `lg` 1024, `xl` 1280). The sidebar becomes a drawer below
`lg`. Focus is a 2 px saffron outline on `:focus-visible`. Animations are disabled under `prefers-reduced-motion`.
A base rule lets grid and flex-column children shrink (`min-width: 0`), so wide tables scroll inside their own
wrapper rather than widening the page.

## Components

| Component | File | Notes |
|---|---|---|
| App shell | `layouts/AppLayout.tsx` | Sticky header (wordmark, environment badge, alerts with unread count, account menu), trust-notice bar, grouped sidebar, mobile drawer (focus trapped, closes on Escape or navigation), skip link, `main#main-content` |
| Brand | `components/BrandMark.tsx` | Original mark (document + lens) and `Wordmark` with "Regulatory Scrutiny Assistance". Also `public/favicon.svg` |
| Navigation | `app/navigation.ts` | `NAV_GROUPS` (Overview, Scrutiny work, Administration, Support); `adminOnly` items hidden for reviewers (the server still enforces roles) |
| Page header | `PageHeader` | Eyebrow, `h1`, description, actions, `Breadcrumbs` |
| Buttons | `buttonStyles.{primary,secondary,danger,ghost,link,small}`, `IconButton` | Busy buttons are disabled and relabelled ("Saving…", "Working…") |
| Fields | `TextField`, `PasswordField` (show/hide), `TextArea` (counter), `SelectField`, `Checkbox` | Label, required marker `*`, hint, error with `aria-invalid` / `aria-describedby` |
| Feedback | `Alert` (error/success/info/warning), `ToastProvider` / `useToast`, `LoadingState`, `Skeleton`, `ProgressBar`, `ErrorState` (Retry), `EmptyState` | Toasts confirm completed server actions in a polite live region and never replace inline errors |
| Status | `Badge`, `StatusBadge`, `Pill`, severity and review-state styles in `app/labels.ts` | Text always states the meaning; colour is supplementary |
| Data | `TABLE` styles, `Pagination`, `DefinitionGrid`, `EvidenceQuote` | Tables have captions, sit in a horizontal-scroll wrapper and set a `min-w-[…]` so cells don't collapse on phones |
| Structure | `Card`, `SectionNav` (workspace jump links), `Tabs` (arrow-key tablist) | |
| Overlays | `Dialog`, `ConfirmDialog` | `role="dialog"`, `aria-modal`, focus trap, Escape, focus restore, body scroll lock. `ConfirmDialog` shows the server error inside the dialog and disables both buttons while busy |

## Interaction rules

- **Consequential changes need confirmation.** Deleting a document, disabling or enabling a rule, changing a rule's
  severity, changing a user's role and deactivating or reactivating a user all open a `ConfirmDialog` that states
  the effect. Nothing is sent until the user confirms. A failure keeps the dialog open with the reason.
- **No double submission.** Submit buttons are disabled while their request runs, and handlers return early when busy.
- **Input survives failure.** Forms keep typed values when the server rejects them; field errors are mapped from the
  API's `fieldErrors`.
- **No simulated success.** A success message or toast appears only after the API confirms the change.
- **Dates** use `formatDateTime` (en-IN, medium date, short time, local zone). The audit trail exposes the UTC
  timestamp on hover.
- **Files** open and download through authenticated blob requests; no storage path or public file URL is rendered.

## Routes

`/` Overview · `/review-queue` · `/applications`, `/applications/new`, `/applications/:code` (workspace with
sections: overview, documents, scrutiny and findings, evidence requests, copilot, alerts, activity, institution) ·
`/institutions`, `/institutions/new`, `/institutions/:code` · `/alerts` · `/scrutiny-rules` · `/users` (admin) ·
`/audit-trail` (admin) · `/help` · `/login` · anything else shows the Not found page.

## Responsive and accessibility checks

Verified in a real browser (Edge, `frontend/e2e/smoke.mjs`): no page-level horizontal scroll on every route at 360,
390, 768, 1024, 1440 and 1920 px; dialogs fit a 390 × 844 viewport; long filenames and institution names wrap.
Component tests cover the dialog focus trap and focus restore, Escape, double-submit prevention, the drawer, tabs,
toasts and the password toggle. Contrast was chosen against WCAG AA but has not been audited with a dedicated tool.
