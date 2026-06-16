import secrets

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../.env", ".env"),
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
    )

    # Database. Defaults to a local SQLite file for zero-config local dev.
    # In Docker Compose this is overridden with a PostgreSQL URL.
    DATABASE_URL: str = "sqlite:///./lifeline.db"

    # Auth
    JWT_SECRET: str = secrets.token_urlsafe(32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24h

    # External routing (OpenRouteService). If empty, system falls back to
    # haversine-based ETA so the platform always works offline.
    ORS_API_KEY: str = ""

    # Seed bootstrap values. Passwords should be provided locally through .env.
    # If a password is omitted, the seed script generates and prints a local one.
    SEED_ADMIN_EMAIL: str = "admin@lifeline.ai"
    SEED_ADMIN_PASSWORD: str = ""
    SEED_DISPATCHER_PASSWORD: str = ""
    SEED_DRIVER_PASSWORD: str = ""
    SEED_HOSPITAL_PASSWORD: str = ""
    SEED_CITIZEN_PASSWORD: str = ""

    CORS_ORIGINS: str = "*"


settings = Settings()
