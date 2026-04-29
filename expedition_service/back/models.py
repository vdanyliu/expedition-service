from datetime import datetime

from pydantic import BaseModel

from expedition_service.back.enums import ExpeditionStatus, MemberState, UserRole


class UserCreateModel(BaseModel):
    email: str
    name: str
    role: UserRole


class UserModel(UserCreateModel):
    id: int
    created_at: datetime
    updated_at: datetime


class AuthTokenModel(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserModel


class AuthenticatedUserModel(BaseModel):
    user: UserModel
    expires_at: datetime


class ExpeditionCreateModel(BaseModel):
    title: str
    description: str | None
    capacity: int
    chief_id: int


class ExpeditionModel(ExpeditionCreateModel):
    id: int
    status: ExpeditionStatus
    start_at: datetime
    end_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ExpeditionMemberModel(BaseModel):
    id: int
    expedition_id: int
    user_id: int
    state: MemberState
    invited_at: datetime
    confirmed_at: datetime | None
