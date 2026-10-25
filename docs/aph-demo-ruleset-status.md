# APH Demo Ruleset Status

## Executive status

The APH candidates are wired into scrutiny through an explicitly selected,
isolated `aph_eoa_demo` profile. They are **not** production rules and are not
formally approved. Production remains the default, and its activation path was
not changed. Demo findings are marked `DEMO RULESET - formal approval pending`.

This is a working demo integration, not a completed production-rule migration.
Only R01, R02, and R08 are executable checks in the profile. R04–R07 are
represented as alternatives within R02, not as separate cumulative checks. R03
is omitted as directed. Accordingly, it would be inaccurate to say that all
eight candidate rules are independently running.

## What is wired

- The profile and its versioned rule snapshots are defined in
  [aph_demo_ruleset.py](../backend/app/services/aph_demo_ruleset.py).
- Scrutiny dispatches to the profile only when explicitly requested; the
  production profile remains the default in
  [scrutiny.py](../backend/app/services/scrutiny.py).
- The request/response profile selection is wired through
  [scrutiny.py](../backend/app/api/v1/scrutiny.py) and the scrutiny schemas.
- Structured logs report the selected profile, version, snapshot hash, and rule
  count. The observed selection was:

  ```text
  {"logger":"regulens.scrutiny","message":"Scrutiny ruleset selected","ruleset_profile":"aph_eoa_demo","ruleset_version":"1","rule_set_version":"6f5d2c654704","rule_count":3,...}
  ```

- The UI exposes an explicit demo-profile choice and displays the demo warning
  and available rule citations. Finding detail and PDF reports include the
  candidate citations and demo notice.
- The implementation and limitations are documented in
  [scrutiny-and-extraction.md](./scrutiny-and-extraction.md) and
  [api-contracts.md](./api-contracts.md).

## Same-packet before/after run

The captured baseline and demo-profile results are in the session artifacts
`aph-demo-before.json` and `aph-demo-after.json`. Both runs used the same
synthetic packets:

| Packet | Application | Before | After using `aph_eoa_demo` |
|---|---|---|---|
| A — clean | `REG-EoA-2026-0001` | 1 finding: DAT-002 inconclusive | R08, R01, R02 all inconclusive |
| B — inconsistent | `REG-EoA-2026-0005` | 5 findings: CON-003 issue, CON-005 issue, CON-003 inconclusive, DAT-002 inconclusive, and a system anomaly | R08, R01, R02 all inconclusive, plus a system anomaly |
| C — unreadable/ambiguous | `REG-EoA-2026-0008` | 9 findings from the existing scrutiny rules | R08, R01, R02 all inconclusive |

Every APH finding in the after run carried the required demo-pending notice.
The packet fixtures have no `submitted_at` value. Therefore, date-dependent
validity checks correctly stayed inconclusive rather than inventing a
reference date. R08 also could not assess the building-age trigger without
completion-certificate evidence. For packet C, the fire certificate had no
usable text layer and OCR was unavailable, so R01 was inconclusive as well.
These runs prove profile dispatch and finding creation; they do **not** prove
that the APH checks can resolve real application evidence or produce positive
findings with complete dates.

## Approval and provenance boundary

The demo profile intentionally bypasses formal activation only for this
labelled demonstration. It does not insert these candidates into the production
rule set or mark them approved. The stored citations refer to local candidate
metadata; they are not an independent authentication of the source document or
a formal regulatory interpretation. Do not present demo outcomes as approval,
rejection, or a determination of misconduct.

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
separate from the APH demo-profile packet results above, but must be fixed and
retested before describing the overall registry implementation as fully
validated.

## Overall assessment

**Demo pipeline integration: implemented and exercised. Production APH rule
replacement/activation: not done. End-to-end evidence evaluation: incomplete**
because the supplied packets lack submission dates and some required readable
documents. The next meaningful validation is to fix the issuer-authority test
failure, provide synthetic fixtures with explicit submission dates and
readable certificate evidence, and verify expected positive/inconclusive
outcomes without changing production activation.
