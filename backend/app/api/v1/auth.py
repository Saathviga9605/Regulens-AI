"""Authentication (public login) and administrator-only user management."""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import bearer_token, get_app_settings, get_current_actor, get_db, require_admin
from app.core.config import Settings
from app.core.context import Actor
from app.models import User
from app.schemas.workspace import LoginRequest, LoginResponse, UserCreate, UserRead, UserUpdate
from app.services import auth as service

public_router = APIRouter(prefix="/auth", tags=["auth"])
router = APIRouter(tags=["auth"])


@public_router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Session = Depends(get_db), settings: Settings = Depends(get_app_settings)) -> LoginResponse:
    token, auth_session, user = service.login(db, settings, body.username, body.password)
    return LoginResponse(token=token, expires_at=auth_session.expires_at, user=UserRead.model_validate(user))


@router.post("/auth/logout", status_code=204, response_class=Response)
def logout(request: Request, db: Session = Depends(get_db)) -> Response:
    service.logout(db, bearer_token(request) or "")
    return Response(status_code=204)


@router.get("/auth/me", response_model=UserRead)
def me(actor: Actor = Depends(get_current_actor), db: Session = Depends(get_db)) -> UserRead:
    return UserRead.model_validate(db.get(User, actor.user_id))


@router.get("/users", response_model=list[UserRead], dependencies=[Depends(require_admin)])
def list_users(db: Session = Depends(get_db)) -> list[UserRead]:
    return [UserRead.model_validate(u) for u in service.list_users(db)]


@router.post("/users", response_model=UserRead, status_code=201, dependencies=[Depends(require_admin)])
def create_user(body: UserCreate, db: Session = Depends(get_db)) -> UserRead:
    return UserRead.model_validate(service.create_user(db, username=body.username, display_name=body.display_name,
                                                       role=body.role, password=body.password))


@router.patch("/users/{user_id}", response_model=UserRead)
def update_user(user_id: str, body: UserUpdate, actor: Actor = Depends(require_admin),
                db: Session = Depends(get_db)) -> UserRead:
    return UserRead.model_validate(service.update_user(db, user_id, actor, **body.model_dump(exclude_unset=True)))
