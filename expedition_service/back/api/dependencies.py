from collections.abc import Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from expedition_service.back.models import UserModel
from expedition_service.back.platform.errors import DomainError
from expedition_service.back.service.auth import AuthService

security = HTTPBearer(auto_error=False)


def create_current_user_dependency(auth_service: AuthService) -> Callable:
    async def get_current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(security),
    ) -> UserModel:
        if credentials is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
        if credentials.scheme != "Bearer":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid authorization scheme")
        try:
            return await auth_service.get_user_by_token(credentials.credentials)
        except DomainError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    return get_current_user
