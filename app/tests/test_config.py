import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_cors_origins_accept_comma_separated_environment_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CORS_ORIGINS", "https://app.example,https://admin.example")
    configured = Settings(_env_file=None)

    assert configured.CORS_ORIGINS == [
        "https://app.example",
        "https://admin.example",
    ]


def test_production_rejects_the_development_secret() -> None:
    with pytest.raises(ValidationError, match="SECRET_KEY must be configured"):
        Settings(_env_file=None, ENVIRONMENT="production")
