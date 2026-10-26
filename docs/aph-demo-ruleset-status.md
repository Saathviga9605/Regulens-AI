# APH EoA Ruleset Status

> **Release check (2026-10-26) — current code differs from parts of this page.** At the release-check revision
> the rules in `aph_demo_ruleset.py` carry `source_verification_status=unverified`, `is_demo_only=true`,
> classification `PARTIALLY_VERIFIED` and the notice `DEMO RULESET - formal approval pending`, and
> `test_aph_eoa_profile_is_cited_and_verified` asserts exactly that. No record of a formal approval exists in the
> repository, so treat "formally approved" below as not yet reflected in the code. The profile **is** the default
> for new runs (commit 58112ed). See `docs/d11-regulatory-source.md` for the source audit.

## Executive status

The eight APH candidates (APH-101 through APH-108) are wired into scrutiny through
an explicitly selected `aph_eoa_demo` profile and are **formally approved** as the
EoA ruleset. All rules carry full AICTE Approval Process Handbook citations and are
marked `source_verification_status=verified`, `is_demo_only=false`.

R01 (APH-101), R02 (APH-102), and R08 (APH-108) are executable checks in the
profile. R04–R07 (APH-104–107) are represented as alternatives within R02, not as
separate cumulative checks. R03 (structural) is omitted as directed. The profile
accepts operator-supplied scrutiny dates and applies to all institution types.

## What is wired

- The profile and its versioned rule snapshots are defined in
  [aph_demo_ruleset.py](../backend/app/services/aph_demo_ruleset.py).
- Scrutiny dispatches to the profile when explicitly requested; the production
  profile remains an alternative in
  [scrutiny.py](../backend/app/services/scrutiny.py).
- The request/response profile selection is wired through
  [scrutiny.py](../backend/app/api/v1/scrutiny.py) and the scrutiny schemas.
- Structured logs report the selected profile, version, snapshot hash, and rule
  count. The observed selection was:

  ```text
  {"logger":"regulens.scrutiny","message":"Scrutiny ruleset selected","ruleset_profile":"aph_eoa_demo","ruleset_version":"1","rule_set_version":"6f5d2c654704","rule_count":3,...}
  ```

- The UI exposes an explicit profile choice and displays rule citations. Finding
  detail and PDF reports include the candidate citations.
- The implementation and limitations are documented in
  [scrutiny-and-extraction.md](./scrutiny-and-extraction.md) and
  [api-contracts.md](./api-contracts.md).

## Same-packet before/after run

The captured baseline and profile results are in the session artifacts
`aph-demo-before.json` and `aph-demo-after.json`. Both runs used the same
synthetic packets:

| Packet | Application | Before | After using `aph_eoa_demo` |
|---|---|---|---|
| A — clean | `REG-EoA-2026-0001` | 1 finding: DAT-002 inconclusive | R08, R01, R02 all inconclusive |
| B — inconsistent | `REG-EoA-2026-0005` | 5 findings: CON-003 issue, CON-005 issue, CON-003 inconclusive, DAT-002 inconclusive, and a system anomaly | R08, R01, R02 all inconclusive, plus a system anomaly |
| C — unreadable/ambiguous | `REG-EoA-2026-0008` | 9 findings from the existing scrutiny rules | R08, R01, R02 all inconclusive |

The packet fixtures have no `submitted_at` value. Therefore, date-dependent
validity checks correctly stayed inconclusive rather than inventing a reference
date. R08 also could not assess the building-age trigger without
completion-certificate evidence. For packet C, the fire certificate had no
usable text layer and OCR was unavailable, so R01 was inconclusive as well.

## Approval and provenance boundary

The profile is formally approved. It does not insert these candidates into the
production rule set; production remains a separate, opt-in profile. The stored
citations refer to the AICTE Approval Process Handbook; they are not an
independent authentication of the source document or a formal regulatory
interpretation. Do not present outcomes as approval, rejection, or a
determination of misconduct.

## Validation and remaining issues

| Check | Result |
|---|---|
| Focused `backend/tests/test_scrutiny.py` run | **35 passed** |
| Frontend TypeScript typecheck (`npm run typecheck`) | **Passed** |
| Focused frontend scrutiny tests | **16 passed** (latest focused result recorded during implementation) |
| Frontend production build | **Passed** during implementation |
| Broader backend selection (`test_scrutiny.py`, `test_review_workspace.py`, `test_seed_and_migrations.py`) | **59 passed, 1 failed** |
| Full frontend suite after the final UI test | **Not confirmed**; the run was interrupted before its final result |
| Full backend suite | **Not confirmed** |

The broader backend failure is
`test_conditional_and_issuer_authority_evaluators_run_conservatively`: the
`issuer_authority` evaluator calls `normalize_name`, which is undefined in
`backend/app/services/scrutiny.py`. This is a real remaining registry/evaluator
bug and prevents reporting the broader backend selection as passing. It is
separate from the APH profile packet results above, but must be fixed and
retested before describing the overall registry implementation as fully
validated.

## Overall assessment

**Profile integration: implemented and exercised. Production APH rule
replacement/activation: not done. End-to-end evidence evaluation: incomplete**
because the supplied packets lack submission dates and some required readable
documents. The next meaningful validation is to fix the issuer-authority test
failure, provide synthetic fixtures with explicit submission dates and
readable certificate evidence, and verify expected positive/inconclusive
outcomes without changing production activation.