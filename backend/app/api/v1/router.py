from fastapi import APIRouter

from app.api.v1 import applications, institutions, system

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(institutions.router)
api_router.include_router(applications.router)
