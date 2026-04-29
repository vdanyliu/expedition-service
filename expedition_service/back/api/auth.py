from fastapi import APIRouter, status

from expedition_service.back.api.requests import LoginRequest, RegisterRequest
from expedition_service.back.api.responses import TokenResponse
from expedition_service.back.service.auth import AuthService


def create_router(service: AuthService) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["auth"])

    @router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
    async def register(request: RegisterRequest) -> TokenResponse:
        return TokenResponse.from_model(await service.register(request.to_model()))

    @router.post("/login", response_model=TokenResponse)
    async def login(request: LoginRequest) -> TokenResponse:
        return TokenResponse.from_model(await service.login(request.username))

    return router
