from fastapi import APIRouter, Depends

from app.api.deps import get_current_actor
from app.api.v1 import applications, auth, documents, institutions, reuse, scrutiny, system, workspace

api_router = APIRouter()
# Public: health/system info and login.
api_router.include_router(system.router)
api_router.include_router(auth.public_router)
# Everything else requires a signed-in user; admin-only routes add `require_admin`.
protected = [Depends(get_current_actor)]
for module in (auth, institutions, applications, documents, scrutiny, workspace, reuse):
    api_router.include_router(module.router, dependencies=protected)
# Cross-case match details: every route additionally requires the cross-case reviewer permission.
api_router.include_router(reuse.restricted_router, dependencies=protected)
api_router.include_router(reuse.evaluation_router, dependencies=protected)
