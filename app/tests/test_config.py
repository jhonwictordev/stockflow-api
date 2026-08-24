import pytest
from pydantic import ValidationError

from app.core.config import Settings

PRODUCTION_SETTINGS = {
    "ENVIRONMENT": "production",
    "DATABASE_URL": "postgresql+asyncpg://app:unique-db-secret@db/prod",
    "SECRET_KEY": "X7r!29_aBcD-efGhIjKlMnOpQrStUvWxYz0123456789",
    "ALLOWED_HOSTS": ["api.example.com"],
    "CORS_ORIGINS": ["https://app.example.com"],
}


def test_cors_origins_accept_comma_separated_environment_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example,https://admin.example")
    configured = Settings(_env_file=None)

    assert configured.CORS_ORIGINS == [
        "https://app.example",
        "https://admin.example",
    ]


def test_secret_key_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRET_KEY")
    with pytest.raises(ValidationError, match="SECRET_KEY"):
        Settings(_env_file=None)


def test_production_rejects_a_known_placeholder_secret() -> None:
    with pytest.raises(ValidationError, match="random production secret"):
        Settings(
            _env_file=None,
            **{
                **PRODUCTION_SETTINGS,
                "SECRET_KEY": (
                    "replace-with-a-long-random-secret-of-at-least-32-characters"
                ),
            },
        )


def test_production_rejects_default_database_credentials() -> None:
    with pytest.raises(ValidationError, match="database credentials"):
        Settings(
            _env_file=None,
            **{
                **PRODUCTION_SETTINGS,
                "DATABASE_URL": (
                    "postgresql+asyncpg://stockflow:stockflow@db/stockflow"
                ),
            },
        )


def test_production_rejects_non_https_cors_origin() -> None:
    with pytest.raises(ValidationError, match="HTTPS production origins"):
        Settings(
            _env_file=None,
            **{
                **PRODUCTION_SETTINGS,
                "CORS_ORIGINS": ["http://app.example.com"],
            },
        )


def test_production_disables_api_documentation_by_default() -> None:
    configured = Settings(_env_file=None, **PRODUCTION_SETTINGS)

    assert configured.docs_enabled is False
