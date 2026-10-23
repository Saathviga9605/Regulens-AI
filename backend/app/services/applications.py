"""EoA application management. See docs/data-model.md for the business rules."""

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, contains_eager, selectinload

from app.core.errors import AppError, ConflictError, NotFoundError
from app.db.types import utcnow
from app.models import Application, ApplicationProgramme, Institution
from app.models.enums import ApplicationStatus, ApplicationType, RecordStatus
from app.schemas.application import (
    ApplicationCreate,
    ApplicationListItem,
    ApplicationRead,
    ApplicationUpdate,
    ProgrammeIn,
)
from app.schemas.institution import InstitutionSummary
from app.services import workflow
from app.services.codes import next_application_code
from app.services.querying import LIKE_ESCAPE, contains_pattern, paginate


def _validation_error(field: list[str], message: str) -> AppError:
    return AppError(422, "validation_error", message, [{"loc": ["body", *field], "msg": message}])


def _resolve_institution(session: Session, institution_code: str) -> Institution:
    institution = session.execute(
        select(Institution).where(Institution.institution_code == institution_code)
    ).scalar_one_or_none()
    if institution is None:
        raise AppError(
            404,
            "institution_not_found",
            f"Institution '{institution_code}' was not found.",
            [{"loc": ["body", "institution_code"], "msg": "Institution not found."}],
        )
    if institution.status != RecordStatus.ACTIVE:
        raise ConflictError("institution_inactive", f"Institution '{institution_code}' is inactive.")
    return institution


def _check_programmes(application_type: ApplicationType, programmes: list[ProgrammeIn]) -> None:
    seen: set[tuple] = set()
    for i, p in enumerate(programmes):
        key = (p.programme_level, p.course_name.casefold(), p.shift)
        if key in seen:
            raise _validation_error(["programmes", str(i), "course_name"], "Duplicate programme in this application.")
        seen.add(key)

    def fail(i: int, field: str, message: str) -> AppError:
        return _validation_error(["programmes", str(i), field], message)

    for i, p in enumerate(programmes):
        if application_type != ApplicationType.INTRODUCTION_OF_NEW_COURSE and p.existing_intake == 0:
            raise fail(i, "existing_intake", "Existing intake must be greater than 0 for an existing programme.")
        if p.proposed_intake == 0:
            raise fail(i, "proposed_intake", "Proposed intake must be greater than 0.")

    if application_type == ApplicationType.INCREASE_IN_INTAKE and not any(
        p.proposed_intake > p.existing_intake for p in programmes
    ):
        raise fail(0, "proposed_intake", "At least one programme must propose an increased intake.")
    if application_type == ApplicationType.REDUCTION_IN_INTAKE and not any(
        p.proposed_intake < p.existing_intake for p in programmes
    ):
        raise fail(0, "proposed_intake", "At least one programme must propose a reduced intake.")
    if application_type == ApplicationType.INTRODUCTION_OF_NEW_COURSE and not any(
        p.existing_intake == 0 for p in programmes
    ):
        raise fail(0, "existing_intake", "At least one programme must be new (existing intake 0).")
    if application_type in (ApplicationType.EOA_NO_CHANGE, ApplicationType.CHANGE_OF_INSTITUTION_NAME):
        for i, p in enumerate(programmes):
            if p.proposed_intake != p.existing_intake:
                raise fail(i, "proposed_intake", "Proposed intake must equal existing intake for this application type.")


def _programme_rows(programmes: list[ProgrammeIn]) -> list[ApplicationProgramme]:
    return [ApplicationProgramme(position=i, **p.model_dump()) for i, p in enumerate(programmes)]


def _snapshot(institution: Institution) -> dict:
    return {
        "institution_code": institution.institution_code,
        "name": institution.name,
        "institution_type": institution.institution_type.value,
        "state": institution.state,
        "district": institution.district,
        "address": institution.address,
        "trust_name": institution.trust_name,
        "property_identifier": institution.property_identifier,
        "captured_at": utcnow().isoformat(),
    }


def _with_relations():
    return (
        select(Application)
        .join(Application.institution)
        .options(contains_eager(Application.institution), selectinload(Application.programmes))
    )


def create_application(session: Session, data: ApplicationCreate, *, seed_key: str | None = None) -> Application:
    institution = _resolve_institution(session, data.institution_code)
    _check_programmes(data.application_type, data.programmes)
    application = Application(
        application_code=next_application_code(session, data.academic_year),
        institution=institution,
        category=data.category,
        academic_year=data.academic_year,
        application_type=data.application_type,
        status=ApplicationStatus.DRAFT,
        programmes=_programme_rows(data.programmes),
        seed_key=seed_key,
    )
    session.add(application)
    session.commit()
    return get_application(session, application.application_code)


def get_application(session: Session, application_code: str) -> Application:
    application = (
        session.execute(_with_relations().where(Application.application_code == application_code))
        .unique()
        .scalar_one_or_none()
    )
    if application is None:
        raise NotFoundError(f"Application '{application_code}' was not found.")
    return application


def list_applications(
    session: Session,
    *,
    page: int,
    page_size: int,
    q: str | None = None,
    status: ApplicationStatus | None = None,
    academic_year: str | None = None,
    application_type: ApplicationType | None = None,
    institution_code: str | None = None,
) -> tuple[list[Application], int]:
    stmt = _with_relations()
    if q:
        pattern = contains_pattern(q.strip())
        stmt = stmt.where(
            or_(
                func.lower(Application.application_code).like(pattern, escape=LIKE_ESCAPE),
                Institution.name_normalized.like(pattern, escape=LIKE_ESCAPE),
                func.lower(Institution.institution_code).like(pattern, escape=LIKE_ESCAPE),
            )
        )
    if status:
        stmt = stmt.where(Application.status == status)
    if academic_year:
        stmt = stmt.where(Application.academic_year == academic_year)
    if application_type:
        stmt = stmt.where(Application.application_type == application_type)
    if institution_code:
        stmt = stmt.where(Institution.institution_code == institution_code)
    stmt = stmt.order_by(Application.created_at.desc(), Application.application_code.desc())
    return paginate(session, stmt, page, page_size)


def update_application(session: Session, application_code: str, data: ApplicationUpdate) -> Application:
    application = get_application(session, application_code)
    if not workflow.is_editable(application.status):
        raise ConflictError(
            "application_frozen",
            "Only draft applications can be edited. Return the application to draft first, if permitted.",
        )
    changes = data.model_dump(exclude_unset=True)
    if not changes:
        return application

    # Validate everything before mutating, so a failed update leaves the record untouched.
    new_type = data.application_type or application.application_type
    new_programmes = data.programmes if data.programmes is not None else [
        ProgrammeIn.model_validate(p, from_attributes=True) for p in application.programmes
    ]
    _check_programmes(new_type, new_programmes)
    institution = _resolve_institution(session, data.institution_code) if data.institution_code else None

    if institution is not None:
        application.institution = institution
    if data.academic_year:
        application.academic_year = data.academic_year
    if data.application_type:
        application.application_type = data.application_type
    if data.programmes is not None:
        application.programmes.clear()
        session.flush()  # delete old rows before inserting replacements (unique constraint)
        application.programmes.extend(_programme_rows(data.programmes))
    application.updated_at = utcnow()
    session.commit()
    return get_application(session, application_code)


def change_status(session: Session, application_code: str, target: ApplicationStatus) -> Application:
    application = get_application(session, application_code)
    current = application.status
    if not workflow.can_transition(current, target):
        allowed = workflow.allowed_transitions(current)
        raise ConflictError(
            "invalid_status_transition",
            f"Cannot change status from '{current.value}' to '{target.value}'.",
            [{"allowed_transitions": [s.value for s in allowed]}],
        )

    now = utcnow()
    if target == ApplicationStatus.READY_FOR_PRELIMINARY_SCRUTINY:
        if application.institution.status != RecordStatus.ACTIVE:
            raise ConflictError("institution_inactive", "The linked institution is inactive.")
        application.submitted_at = now
        application.institution_snapshot = _snapshot(application.institution)
    elif target == ApplicationStatus.DRAFT:
        application.submitted_at = None
        application.institution_snapshot = None

    application.status = target
    application.status_changed_at = now
    application.updated_at = now
    session.commit()
    return get_application(session, application_code)


def to_list_item(application: Application) -> ApplicationListItem:
    return ApplicationListItem(
        application_code=application.application_code,
        category=application.category,
        academic_year=application.academic_year,
        application_type=application.application_type,
        status=application.status,
        institution=InstitutionSummary.model_validate(application.institution),
        programme_count=len(application.programmes),
        total_proposed_intake=sum(p.proposed_intake for p in application.programmes),
        submitted_at=application.submitted_at,
        created_at=application.created_at,
        updated_at=application.updated_at,
    )


def to_read(application: Application) -> ApplicationRead:
    return ApplicationRead(
        **to_list_item(application).model_dump(),
        programmes=application.programmes,
        status_changed_at=application.status_changed_at,
        is_editable=workflow.is_editable(application.status),
        document_intake_open=workflow.document_intake_open(application.status),
        allowed_transitions=workflow.allowed_transitions(application.status),
        institution_snapshot=application.institution_snapshot,
    )
