from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from expedition_service.back.platform.config import Settings


@dataclass(frozen=True)
class AccessTokenPayload:
    user_id: int
    expires_at: datetime


class JwtTokenService:
    def __init__(self, settings: Settings):
        self.settings = settings

    def create_access_token(self, user_id: int) -> str:
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=self.settings.access_token_expire_minutes)
        payload = {
            "sub": str(user_id),
            "exp": expires_at,
        }
        return jwt.encode(payload, self.settings.jwt_secret_key, algorithm=self.settings.jwt_algorithm)

    def decode_access_token(self, token: str) -> int:
        return self.decode_access_token_payload(token).user_id

    def decode_access_token_payload(self, token: str) -> AccessTokenPayload:
        payload = jwt.decode(token, self.settings.jwt_secret_key, algorithms=[self.settings.jwt_algorithm])
        try:
            user_id = int(payload["sub"])
            expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        except (KeyError, TypeError, ValueError) as exc:
            raise JWTError("Invalid token payload") from exc
        return AccessTokenPayload(user_id=user_id, expires_at=expires_at)
