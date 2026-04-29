from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    jwt_secret_key: str
    jwt_algorithm: str
    access_token_expire_minutes: int
    websocket_cleanup_interval_seconds: int


def get_settings() -> Settings:
    return Settings(
        database_url="sqlite+aiosqlite:///./expedition_service.db",
        jwt_secret_key="expedition-service-dev-secret",
        jwt_algorithm="HS256",
        access_token_expire_minutes=120,
        websocket_cleanup_interval_seconds=30,
    )
