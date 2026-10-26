# D11 — Regulatory source and rule audit

## Pinned source
See `rules-registry/source/SOURCE.md` and `backend/app/regulatory/aph_2024_27.json` (SHA-256 `153d5481…6051`, 231 pages).

## Rule audit

| Rule(s) | Profile | Classification | Reason |
|---|---|---|---|
| R01, R08 | `aph_eoa_demo` v2 | PARTIALLY_VERIFIED | Quote verified (PDF p. 97 / printed p. 81); validity or reference date is ReguLens' interpretation |
| R02 | `aph_eoa_demo` v2 | PARTIALLY_VERIFIED | Quote verified; cross-reference "Clause 7.17" unresolved |
| Production-profile demo rules | production | DEMO_ONLY | No handbook citation |
| Consistency checks | production | INTEGRITY_CHECK | Generic checks, not regulatory rules |
| Retired rules | production | RETIRED | Kept for history only |

No rule is classified SOURCE_VERIFIED: every cited rule involves some interpretation. Rule logic is unchanged from
version 1; only provenance changed. D11 promoted no draft rules and did not change the default profile. (Separately, commit 58112ed made `aph_eoa_demo` the default for new runs; see `docs/d9-acceptance.md`, release check.)

## Provenance
Run snapshots of APH rules now record `source_id`, `source_version`, `source_sha256`, classification and
interpretation. The preliminary report prints the source title, hash prefix, rule version and classification.
Snapshots made with version 1 are left unchanged.

## What verification means
Matching the pinned hash and finding the quotations proves the integrity of that one source file and the presence
of the cited text. It does not rule out later amendments or corrigenda, and it is not approval of any rule
(see `docs/d9-acceptance.md`, team decision B).

## No migration
The changes are code and data only, so D11 adds no schema migration.

## UI copy
The repeated trust bar, environment badge, dashboard purpose banner and status panel, Help "About this prototype"
alert and login demo banner were removed. One identity statement remains, in the app footer, on the sign-in page
and in Help → About. Backend status moved to Help → System status, and the sidebar indicator appears only when the
backend is unhealthy. Contextual labels (SIMULATED, NOT_CONNECTED, demo-only) are kept.
