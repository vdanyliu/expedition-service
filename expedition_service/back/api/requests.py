from pydantic import BaseModel, Field, field_validator

from expedition_service.back.enums import ExpeditionStatus, UserRole
from expedition_service.back.models import ExpeditionCreateModel, UserCreateModel


class RegisterRequest(BaseModel):
    email: str
    name: str
    role: UserRole

    @field_validator("email", "name", mode="before")
    @classmethod
    def normalize_required_string(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("email", "name")
    @classmethod
    def validate_required_string(cls, value: str) -> str:
        if not value:
            raise ValueError("Field must not be empty.")
        return value

    def to_model(self) -> UserCreateModel:
        return UserCreateModel(email=self.email, name=self.name, role=self.role)


class LoginRequest(BaseModel):
    username: str

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        if not value:
            raise ValueError("username must not be empty.")
        return value


class ExpeditionCreateRequest(BaseModel):
    title: str
    description: str | None = None
    capacity: int = Field(gt=0)

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value):
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if not value:
            raise ValueError("title must not be empty.")
        return value

    @field_validator("description", mode="before")
    @classmethod
    def normalize_description(cls, value):
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        return value

    def to_model(self, chief_id: int) -> ExpeditionCreateModel:
        return ExpeditionCreateModel(
            title=self.title,
            description=self.description,
            capacity=self.capacity,
            chief_id=chief_id,
        )


class InviteMemberRequest(BaseModel):
    user_id: int = Field(gt=0)


class ExpeditionStatusUpdateRequest(BaseModel):
    status: ExpeditionStatus
