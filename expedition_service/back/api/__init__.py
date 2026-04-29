from fastapi import APIRouter

from expedition_service.back.api.auth import create_router as auth_router
from expedition_service.back.api.dependencies import create_current_user_dependency
from expedition_service.back.api.expeditions import create_router as expeditions_router
from expedition_service.back.api.operational import create_operational_api
from expedition_service.back.api.websockets import create_router as websocket_router
from expedition_service.back.platform.events import ExpeditionEventManager
from expedition_service.back.service.auth import AuthService
from expedition_service.back.service.expeditions import ExpeditionService


def create_router(
    auth_service: AuthService,
    expedition_service: ExpeditionService,
    events: ExpeditionEventManager,
) -> APIRouter:
    router = APIRouter()
    current_user_dependency = create_current_user_dependency(auth_service)
    router.include_router(create_operational_api())
    router.include_router(auth_router(auth_service))
    router.include_router(expeditions_router(expedition_service, current_user_dependency))
    router.include_router(websocket_router(auth_service, events))
    return router
