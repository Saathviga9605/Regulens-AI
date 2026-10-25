"""Source-verification status (Project Bible v3.0 amendment labels) and source type.

This dimension answers only: *what did an external source say about this document?* It is kept separate from
the rule outcome (scrutiny rules), the evidence state (extracted/not found/ambiguous/unverified), the human reviewer
disposition, and the cross-case reuse outcome.

Source type:
* ``LIVE`` — a real connection to an issuing authority. **No live adapter exists in ReguLens**; this value is never
  produced and is defined only so the contract is complete.
* ``SIMULATED`` — the synthetic demo registry (``MockIssuerAdapter``). Never a real check.
* ``NOT_CONNECTED`` — no source covers this document type; nothing was checked.

Mapping from the adapter outcome (see ``map_outcome``):

| adapter outcome         | status                  |
|-------------------------|-------------------------|
| simulated_match         | Verified                |
| simulated_mismatch      | Mismatch detected       |
| simulated_expired       | Expired                 |
| simulated_unavailable   | Source unavailable      |
| manual_review           | Manual review required  |
| unsupported             | Manual review required (source type NOT_CONNECTED) |
| no attempt yet          | Verification pending    |
"""

from __future__ import annotations

from app.models.enums import IssuerSourceStatus as S, SourceType, VerificationOutcome as V

LABELS: dict[S, str] = {
    S.VERIFIED: "Verified",
    S.MISMATCH_DETECTED: "Mismatch detected",
    S.EXPIRED: "Expired",
    S.VERIFICATION_PENDING: "Verification pending",
    S.SOURCE_UNAVAILABLE: "Source unavailable",
    S.MANUAL_REVIEW_REQUIRED: "Manual review required",
}

_MAP: dict[V, S] = {
    V.SIMULATED_MATCH: S.VERIFIED,
    V.SIMULATED_MISMATCH: S.MISMATCH_DETECTED,
    V.SIMULATED_EXPIRED: S.EXPIRED,
    V.SIMULATED_UNAVAILABLE: S.SOURCE_UNAVAILABLE,
    V.MANUAL_REVIEW: S.MANUAL_REVIEW_REQUIRED,
    V.UNSUPPORTED: S.MANUAL_REVIEW_REQUIRED,
}


def map_outcome(outcome: V, simulated: bool) -> tuple[S, SourceType]:
    status = _MAP[outcome]
    if outcome == V.UNSUPPORTED:
        return status, SourceType.NOT_CONNECTED
    # Every existing adapter is simulated. A LIVE type would require an adapter that really contacts the issuer.
    return status, SourceType.SIMULATED if simulated else SourceType.LIVE


def pending(category_supported: bool) -> tuple[S, SourceType]:
    """Status for a document with no verification attempt yet."""
    return S.VERIFICATION_PENDING, SourceType.SIMULATED if category_supported else SourceType.NOT_CONNECTED


def display(status: S, source_type: SourceType) -> str:
    return f"{LABELS[status]} ({source_type.value})"
