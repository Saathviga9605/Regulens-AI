from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import Pagination, get_db, get_pagination
from app.models.enums import RecordStatus
from app.schemas.common import Page
from app.schemas.institution import InstitutionCreate, InstitutionRead, InstitutionUpdate
from app.services import institutions as service

router = APIRouter(prefix="/institutions", tags=["institutions"])


@router.post("", response_model=InstitutionRead, status_code=201)
def create_institution(body: InstitutionCreate, db: Session = Depends(get_db)) -> InstitutionRead:
    return InstitutionRead.model_validate(service.create_institution(db, body))


@router.get("", response_model=Page[InstitutionRead])
def list_institutions(
    pagination: Pagination = Depends(get_pagination),
    q: str | None = Query(None, max_length=100, description="Search name or institution code"),
    state: str | None = Query(None, max_length=80),
    status: RecordStatus | None = None,
    db: Session = Depends(get_db),
) -> Page[InstitutionRead]:
    rows, total = service.list_institutions(
        db, page=pagination.page, page_size=pagination.page_size, q=q, state=state, status=status
    )
    return Page.build([InstitutionRead.model_validate(r) for r in rows], total, pagination.page, pagination.page_size)


@router.get("/{institution_code}", response_model=InstitutionRead)
def get_institution(institution_code: str, db: Session = Depends(get_db)) -> InstitutionRead:
    return InstitutionRead.model_validate(service.get_institution(db, institution_code))


@router.patch("/{institution_code}", response_model=InstitutionRead)
def update_institution(institution_code: str, body: InstitutionUpdate, db: Session = Depends(get_db)) -> InstitutionRead:
    return InstitutionRead.model_validate(service.update_institution(db, institution_code, body))
