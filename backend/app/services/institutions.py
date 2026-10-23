import re

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.db.types import utcnow
from app.models import Institution
from app.models.enums import RecordStatus
from app.services import audit
from app.schemas.institution import InstitutionCreate, InstitutionUpdate
from app.services.codes import next_institution_code
from app.services.querying import LIKE_ESCAPE, contains_pattern, paginate


def normalize_name(name: str) -> str:
    return re.sub(r"\s+", " ", name).strip().casefold()


def create_institution(session: Session, data: InstitutionCreate, *, seed_key: str | None = None) -> Institution:
    institution = Institution(
        institution_code=next_institution_code(session),
        name_normalized=normalize_name(data.name),
        seed_key=seed_key,
        **data.model_dump(),
    )
    session.add(institution)
    session.flush()
    audit.record(session, "institution.created", "institution", institution.institution_code)
    session.commit()
    return institution


def get_institution(session: Session, institution_code: str) -> Institution:
    institution = session.execute(
        select(Institution).where(Institution.institution_code == institution_code)
    ).scalar_one_or_none()
    if institution is None:
        raise NotFoundError(f"Institution '{institution_code}' was not found.")
    return institution


def list_institutions(
    session: Session,
    *,
    page: int,
    page_size: int,
    q: str | None = None,
    state: str | None = None,
    status: RecordStatus | None = None,
) -> tuple[list[Institution], int]:
    stmt = select(Institution)
    if q:
        pattern = contains_pattern(q.strip())
        stmt = stmt.where(
            or_(
                Institution.name_normalized.like(pattern, escape=LIKE_ESCAPE),
                func.lower(Institution.institution_code).like(pattern, escape=LIKE_ESCAPE),
            )
        )
    if state:
        stmt = stmt.where(func.lower(Institution.state) == state.strip().lower())
    if status:
        stmt = stmt.where(Institution.status == status)
    stmt = stmt.order_by(Institution.name_normalized, Institution.institution_code)
    return paginate(session, stmt, page, page_size)


def update_institution(session: Session, institution_code: str, data: InstitutionUpdate) -> Institution:
    institution = get_institution(session, institution_code)
    changes = data.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(institution, field, value)
    if "name" in changes:
        institution.name_normalized = normalize_name(changes["name"])
    if changes:
        institution.updated_at = utcnow()
        audit.record(session, "institution.updated", "institution", institution_code,
                     details={"changed": sorted(changes)})
    session.commit()
    return institution
