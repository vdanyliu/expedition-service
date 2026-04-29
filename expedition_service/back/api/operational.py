import os

from fastapi import APIRouter
from starlette.responses import Response


def create_operational_api() -> APIRouter:
    router = APIRouter()

    @router.get("/health", tags=["operational"], summary="healthcheck")
    def health():
        return Response(status_code=200)

    @router.get("/info", tags=["operational"], summary="info")
    def info():
        return {
            "name": "Expedition Service",
            "version": os.getenv("APP_VERSION"),
        }

    return router
