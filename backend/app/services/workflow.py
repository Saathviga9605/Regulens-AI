"""Internal application workflow. These statuses are ReguLens prototype states, never AICTE decisions.

Moving into preliminary scrutiny is a prototype transition only: document intake and
validation do not exist yet, so it does not prove that required documents are present.
"""

from app.models.enums import ApplicationStatus as S

TRANSITIONS: dict[S, frozenset[S]] = {
    S.DRAFT: frozenset({S.READY_FOR_PRELIMINARY_SCRUTINY}),
    # Returning to draft is the only permitted correction path, and only before scrutiny starts.
    S.READY_FOR_PRELIMINARY_SCRUTINY: frozenset({S.DRAFT, S.UNDER_PRELIMINARY_SCRUTINY}),
    S.UNDER_PRELIMINARY_SCRUTINY: frozenset({S.AWAITING_ADDITIONAL_EVIDENCE, S.PRELIMINARY_SCRUTINY_COMPLETED}),
    S.AWAITING_ADDITIONAL_EVIDENCE: frozenset({S.UNDER_PRELIMINARY_SCRUTINY}),
    S.PRELIMINARY_SCRUTINY_COMPLETED: frozenset(),
}

EDITABLE_STATUSES = frozenset({S.DRAFT})
# Documents may be added/removed while preparing the application or when evidence was requested.
DOCUMENT_INTAKE_STATUSES = (S.DRAFT, S.AWAITING_ADDITIONAL_EVIDENCE)

_ORDER = list(S)


def allowed_transitions(status: S) -> list[S]:
    return sorted(TRANSITIONS[status], key=_ORDER.index)


def can_transition(current: S, target: S) -> bool:
    return target in TRANSITIONS[current]


def is_editable(status: S) -> bool:
    return status in EDITABLE_STATUSES


def document_intake_open(status: S) -> bool:
    return status in DOCUMENT_INTAKE_STATUSES
