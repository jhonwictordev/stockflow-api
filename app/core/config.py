from functools import lru_cache
from typing import Annotated, Literal

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
    APP_VERSION: str = "1.2.2"
    ENVIRONMENT: Literal["development", "test", "production"] = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    API_V1_PREFIX: str = "/api/v1"

    DATABASE_URL: str = "sqlite+aiosqlite:///./inventory.db"

    SECRET_KEY: str = Field(min_length=32)
    JWT_ALGORITHM: Literal["HS256"] = "HS256"
    JWT_ISSUER: str = "stockflow-api"
    JWT_AUDIENCE: str = "stockflow-clients"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30, gt=0)

    AUTH_RATE_LIMIT_REQUESTS: int = Field(default=10, ge=1, le=1_000)
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = Field(default=60, ge=1, le=3_600)
    RATE_LIMIT_MAX_CLIENTS: int = Field(default=10_000, ge=100, le=100_000)
    MAX_REQUEST_BODY_BYTES: int = Field(
        default=1_048_576,
        ge=1_024,
        le=10_485_760,
    )
    ENABLE_DOCS: bool | None = None

    OTEL_ENABLED: bool = False
    OTEL_SERVICE_NAME: str = Field(default="stockflow-api", min_length=1, max_length=63)
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://localhost:4318"
    OTEL_EXPORT_INTERVAL_MILLISECONDS: int = Field(
        default=5_000,
        ge=1_000,
        le=60_000,
    )
    OTEL_EXPORT_TIMEOUT_SECONDS: int = Field(default=10, ge=1, le=60)
    OTEL_TRACE_SAMPLE_RATIO: float = Field(default=1.0, ge=0.0, le=1.0)

    CORS_ORIGINS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://localhost:5173",
        ]
    )
    ALLOWED_HOSTS: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["localhost", "127.0.0.1", "testserver", "test"]
    )

    @field_validator("CORS_ORIGINS", "ALLOWED_HOSTS", mode="before")
    @classmethod
    def parse_csv_list(cls, value: object) -> object:
        if isinstance(value, str) and not value.startswith("["):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @model_validator(mode="after")
    def validate_production_settings(self) -> "Settings":
        if self.ENVIRONMENT != "production":
            return self

        normalized_secret = self.SECRET_KEY.casefold()
        unsafe_secret_markers = (
            "change-me",
            "replace-with",
            "development-only",
            "example-secret",
        )
        if any(marker in normalized_secret for marker in unsafe_secret_markers):
            raise ValueError("SECRET_KEY must be a random production secret")
        if len(set(self.SECRET_KEY)) < 16:
            raise ValueError("SECRET_KEY does not have enough character diversity")

        database_url = self.DATABASE_URL.casefold()
        if not database_url.startswith("postgresql+asyncpg://"):
            raise ValueError("Production requires PostgreSQL with the asyncpg driver")
        if "stockflow:stockflow@" in database_url:
            raise ValueError("Production database credentials must not use defaults")

        unsafe_hosts = {"*", "localhost", "127.0.0.1", "test", "testserver"}
        if not self.ALLOWED_HOSTS or any(
            host.casefold() in unsafe_hosts for host in self.ALLOWED_HOSTS
        ):
            raise ValueError("ALLOWED_HOSTS must contain only production hostnames")
        if any(
            not origin.startswith("https://")
            or "localhost" in origin
            or "127.0.0.1" in origin
            for origin in self.CORS_ORIGINS
        ):
            raise ValueError("CORS_ORIGINS must contain only HTTPS production origins")
        return self

    @property
    def docs_enabled(self) -> bool:
        if self.ENABLE_DOCS is not None:
            return self.ENABLE_DOCS
        return self.ENVIRONMENT != "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
