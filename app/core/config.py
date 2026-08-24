from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or a .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    APP_NAME: str = "StockFlow API"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "sqlite+aiosqlite:///./inventory.db"

    SECRET_KEY: str = Field(
        default="development-only-change-me-at-least-32-chars",
        min_length=32,
    )
    JWT_ALGORITHM: str = "HS256"
    JWT_ISSUER: str = "stockflow-api"
    JWT_AUDIENCE: str = "stockflow-clients"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, gt=0)

    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:5173",
        ]
    )

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: object) -> object:
        if isinstance(value, str) and not value.startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def reject_development_secret_in_production(self) -> "Settings":
        if (
            self.ENVIRONMENT.lower() == "production"
            and self.SECRET_KEY == "development-only-change-me-at-least-32-chars"
        ):
            raise ValueError("SECRET_KEY must be configured for production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
