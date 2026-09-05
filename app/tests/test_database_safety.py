import pytest

from app.tests.conftest import validated_postgres_url


@pytest.mark.parametrize(
    "url",
    [
        None,
        "not-a-url",
        "sqlite:///stockflow_test",
        "postgresql+asyncpg://host/production",
    ],
)
def test_postgres_fixture_refuses_non_test_database(url: str | None) -> None:
    with pytest.raises(pytest.UsageError):
        validated_postgres_url(url)


def test_postgres_fixture_accepts_explicit_dedicated_database() -> None:
    url = "postgresql+asyncpg://localhost/stockflow_test"
    assert validated_postgres_url(url) == url
