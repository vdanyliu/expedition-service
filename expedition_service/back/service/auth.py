from sqlalchemy import select
from jose import JWTError

from expedition_service.back.models import AuthenticatedUserModel, AuthTokenModel, UserCreateModel, UserModel
from expedition_service.back.platform.auth import JwtTokenService
from expedition_service.back.platform.database import Database
from expedition_service.back.platform.db_models import UserRecord
from expedition_service.back.platform.errors import DomainError


class AuthService:
    def __init__(self, db: Database, token_service: JwtTokenService):
        self.db = db
        self.token_service = token_service

    async def register(self, user_model: UserCreateModel) -> AuthTokenModel:
        async with self.db.session() as session:
            existing_user = await session.scalar(select(UserRecord).where(UserRecord.email == user_model.email))
            if existing_user is not None:
                raise DomainError(409, "User already exists")

            user_record = UserRecord(email=user_model.email, name=user_model.name, role=user_model.role)
            session.add(user_record)
            await session.commit()
            await session.refresh(user_record)
            return self._build_token_response(self._to_user_model(user_record))

    async def login(self, email: str) -> AuthTokenModel:
        # Passwordless login is intentional for this test task to keep the sample focused on the expedition domain.
        async with self.db.session() as session:
            user_record = await session.scalar(select(UserRecord).where(UserRecord.email == email))
            if user_record is None:
                raise DomainError(401, "Invalid login")
            return self._build_token_response(self._to_user_model(user_record))

    async def get_user_by_token(self, token: str) -> UserModel:
        return (await self.authenticate_token(token)).user

    async def authenticate_token(self, token: str) -> AuthenticatedUserModel:
        try:
            payload = self.token_service.decode_access_token_payload(token)
        except JWTError as exc:
            raise DomainError(401, "Invalid token") from exc

        async with self.db.session() as session:
            user_record = await session.get(UserRecord, payload.user_id)
            if user_record is None:
                raise DomainError(401, "Invalid token subject")
            return AuthenticatedUserModel(
                user=self._to_user_model(user_record),
                expires_at=payload.expires_at,
            )

    def _build_token_response(self, user: UserModel) -> AuthTokenModel:
        return AuthTokenModel(
            access_token=self.token_service.create_access_token(user.id),
            user=user,
        )

    @staticmethod
    def _to_user_model(user_record: UserRecord) -> UserModel:
        return UserModel(
            id=user_record.id,
            email=user_record.email,
            name=user_record.name,
            role=user_record.role,
            created_at=user_record.created_at,
            updated_at=user_record.updated_at,
        )
