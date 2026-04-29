from fastapi import FastAPI
from fastapi.responses import JSONResponse

from expedition_service.back.api import create_router
from expedition_service.back.helper import LifeSpanHandler
from expedition_service.back.platform.auth import JwtTokenService
from expedition_service.back.platform.config import Settings, get_settings
from expedition_service.back.platform.database import Database
from expedition_service.back.platform.errors import DomainError
from expedition_service.back.platform.events import ExpeditionEventManager
from expedition_service.back.service.auth import AuthService
from expedition_service.back.service.expeditions import ExpeditionService


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    database = Database(resolved_settings)
    events = ExpeditionEventManager(
        cleanup_interval_seconds=resolved_settings.websocket_cleanup_interval_seconds
    )
    token_service = JwtTokenService(resolved_settings)
    lifespan_handler = LifeSpanHandler()
    lifespan_handler.add_span_object(database)
    lifespan_handler.add_span_object(events)
    auth_service = AuthService(db=database, token_service=token_service)
    expedition_service = ExpeditionService(db=database, events=events)

    app = FastAPI(
        title="Expedition Service",
        version="0.1.0",
        lifespan=lifespan_handler.lifespan,
    )

    @app.exception_handler(DomainError)
    async def domain_error_handler(_, exc: DomainError):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    app.include_router(
        create_router(
            auth_service=auth_service,
            expedition_service=expedition_service,
            events=events,
        )
    )
    return app
