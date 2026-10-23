from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import Pagination, get_db, get_pagination
from app.models.enums import ApplicationStatus, ApplicationType
from app.schemas.application import (
    ApplicationCreate,
    ApplicationListItem,
    ApplicationRead,
    ApplicationUpdate,
    StatusChangeRequest,
)
from app.schemas.common import Page
from app.services import applications as service

router = APIRouter(prefix="/applications", tags=["applications"])


@router.post("", response_model=ApplicationRead, status_code=201)
def create_application(body: ApplicationCreate, db: Session = Depends(get_db)) -> ApplicationRead:
    return service.to_read(service.create_application(db, body))


@router.get("", response_model=Page[ApplicationListItem])
def list_applications(
    pagination: Pagination = Depends(get_pagination),
    q: str | None = Query(None, max_length=100, description="Search application ID, institution name or code"),
    status: ApplicationStatus | None = None,
    academic_year: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"),
    application_type: ApplicationType | None = None,
    institution_code: str | None = Query(None, max_length=20),
    db: Session = Depends(get_db),
) -> Page[ApplicationListItem]:
    rows, total = service.list_applications(
        db,
        page=pagination.page,
        page_size=pagination.page_size,
        q=q,
        status=status,
        academic_year=academic_year,
        application_type=application_type,
        institution_code=institution_code,
    )
    return Page.build([service.to_list_item(r) for r in rows], total, pagination.page, pagination.page_size)


@router.get("/{application_code}", response_model=ApplicationRead)
def get_application(application_code: str, db: Session = Depends(get_db)) -> ApplicationRead:
    return service.to_read(service.get_application(db, application_code))


@router.patch("/{application_code}", response_model=ApplicationRead)
def update_application(application_code: str, body: ApplicationUpdate, db: Session = Depends(get_db)) -> ApplicationRead:
    return service.to_read(service.update_application(db, application_code, body))


@router.post("/{application_code}/status", response_model=ApplicationRead)
def change_status(application_code: str, body: StatusChangeRequest, db: Session = Depends(get_db)) -> ApplicationRead:
    return service.to_read(service.change_status(db, application_code, body.target_status))
