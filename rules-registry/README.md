# ReguLens Rules Registry

This workspace separates source evidence, candidate rules, human approvals, and live backend rules.
Only rules with verified source provenance and the required reviewer approvals may be imported as live
regulatory rules. A source extraction is not an approval, and a PDF filename or embedded metadata is
not proof that the file is an authentic or current official edition.

## Current state

- `source/SOURCE.md` records the supplied handbook copy and open verification items.
- `scripts/extract_source.py` extracts exact per-page text to an ignored local file for review.
- `scripts/verify_candidate.py` verifies a draft candidate's source hash, page, exact quote offsets,
  quote hash, OCR flag, and unresolved blockers against that extraction.
- Extracted pages, drafts, and candidates are not committed and are not read by the backend.
- Eight local draft records cover the six individual certificate types in APH Annexure-2 section
  2.1, the four-way alternative group, and its explicit completion-date/structural-certificate
  dependency. They are intentionally blocked on applicability, evaluator, validity-date, or
  document-taxonomy gaps and are not live rules.
- The backend's existing demo/integrity rules remain active until replacements have passed review,
  approval, and import gates. Do not mark an entry verified by changing a status field manually.
- The backend now has a typed one-of document-group evaluator and Building License/Form D categories.
  This is evaluator support only; no APH rule is seeded, approved, imported, or active in scrutiny.

## Local source extraction

From the repository root:

```powershell
python rules-registry\scripts\extract_source.py "docs\APH Final.pdf"
```

The default output is `rules-registry/source/local/pages.jsonl`, which is git-ignored. Each JSONL
record contains the source SHA-256, 1-based PDF page index, exact extracted text, text SHA-256,
character count, extraction method, and OCR flag. Printed page labels are left null unless independently
verified; the extractor does not infer them. An existing output is never overwritten unless `--overwrite`
is explicitly supplied.

This is a text-layer extraction only. Empty or partial text is reported; no OCR text is invented or added.
Review any OCR-required page against the rendered source before citing it. The command's page and character
counts are extraction diagnostics, not proof of completeness or accuracy.

Verify a local candidate against the extracted pages:

```powershell
python rules-registry\scripts\verify_candidate.py rules-registry\candidates\APH-101-fire-safety-certificate.json
```

The verifier establishes only that the draft quote matches the recorded extraction. It does not
authenticate the handbook, establish legal applicability, validate a rule's evaluator, or approve it.

For section 2.1(iii), APH-104 through APH-107 are alternatives in APH-102, not four cumulative
requirements. APH-108 captures only the expressly stated dependency between the Completion
Certificate issue date and the conditional Structural Stability Certificate. No general
cross-document matching requirement is inferred from this clause.

## Promotion boundary

The current backend does not yet have the registry schemas, approval records, immutable version store,
or approved-only importer. Until those gates exist and named authorized reviewers complete review, entries
must remain candidates and must not be used as regulatory findings.
