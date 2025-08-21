# Settings loader
from __future__ import annotations
import secrets
from functools import lru_cache
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database (use SQLite for dev; swap to Postgres URL in prod)
    DATABASE_URL: str = "sqlite:///./inspection_portal.db"

    # S3 / R2 / B2
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_BUCKET_NAME: str = "inspection-reports"
    S3_ENDPOINT_URL: str | None = None  # keep None for AWS S3

    # Auth - Generate secure secret if not provided
    # In production, set this via environment variable
    JWT_SECRET_KEY: str = secrets.token_urlsafe(32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440

    # OpenAI (used by your existing scripts)
    OPENAI_API_KEY: str = ""

    # App
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    class Config:
        env_file = ".env"
        extra = "ignore"

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
