from datetime import datetime

from pydantic import BaseModel

from expedition_service.back.enums import ExpeditionStatus, MemberState, UserRole
from expedition_service.back.models import AuthTokenModel, ExpeditionMemberModel, ExpeditionModel, UserModel


class UserResponse(BaseModel):
    id: int
    email: str
    name: str
    role: UserRole
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, user: UserModel) -> "UserResponse":
        return cls(**user.model_dump())


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserResponse

    @classmethod
    def from_model(cls, token: AuthTokenModel) -> "TokenResponse":
        return cls(
            access_token=token.access_token,
            token_type=token.token_type,
            user=UserResponse.from_model(token.user),
        )


class ExpeditionResponse(BaseModel):
    id: int
    title: str
    description: str | None
    status: ExpeditionStatus
    start_at: datetime
    end_at: datetime | None
    capacity: int
    chief_id: int
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_model(cls, expedition: ExpeditionModel) -> "ExpeditionResponse":
        return cls(**expedition.model_dump())


class ExpeditionMemberResponse(BaseModel):
    id: int
    expedition_id: int
    user_id: int
    state: MemberState
    invited_at: datetime
    confirmed_at: datetime | None

    @classmethod
    def from_model(cls, member: ExpeditionMemberModel) -> "ExpeditionMemberResponse":
        return cls(**member.model_dump())
