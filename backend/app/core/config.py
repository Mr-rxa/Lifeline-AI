from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database. Defaults to a local SQLite file for zero-config local dev.
    # In Docker Compose this is overridden with a PostgreSQL URL.
    DATABASE_URL: str = "sqlite:///./lifeline.db"

    # Auth
    JWT_SECRET: str = "change-me-in-production-lifeline-ai-secret"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24h

    # External routing (OpenRouteService). If empty, system falls back to
    # haversine-based ETA so the platform always works offline.
    ORS_API_KEY: str = ""

    # Default credentials created by the seed script (admin bootstrap).
    SEED_ADMIN_EMAIL: str = "admin@lifeline.ai"
    SEED_ADMIN_PASSWORD: str = "admin123"

    CORS_ORIGINS: str = "*"


settings = Settings()
