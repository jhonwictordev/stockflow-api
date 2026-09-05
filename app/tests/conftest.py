import os
import uuid
from collections.abc import AsyncGenerator, Callable, Coroutine
from pathlib import Path
from typing import Any

os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault(
    "SECRET_KEY",
    "test-suite-secret-with-enough-length-and-character-diversity-123456789",
)
os.environ.setdefault("AUTH_RATE_LIMIT_REQUESTS", "1000")
os.environ["OTEL_ENABLED"] = "false"

import pytest
import pytest_asyncio
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import Connection, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool, StaticPool

from alembic import command
from app.core.database import get_db
from app.main import app
from app.models import Base

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--database", choices=("sqlite", "postgres"), default="sqlite")
    parser.addoption(
        "--evidence-dir", default=None, help="Save synthetic race evidence"
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--database") != "postgres":
        for item in items:
            if "postgres" in item.keywords:
                item.add_marker(pytest.mark.skip(reason="use --database=postgres"))


def validated_postgres_url(value: str | None) -> str:
    if not value:
        raise pytest.UsageError("Set TEST_POSTGRES_URL for --database=postgres")
    try:
        url = make_url(value)
    except Exception:
        raise pytest.UsageError("TEST_POSTGRES_URL is invalid") from None
    if url.drivername != "postgresql+asyncpg" or not (url.database or "").endswith(
        "_test"
    ):
        raise pytest.UsageError(
            "TEST_POSTGRES_URL must use asyncpg and a dedicated database "
            "ending in _test"
        )
    return value


@pytest_asyncio.fixture
async def db_engine(
    request: pytest.FixtureRequest,
) -> AsyncGenerator[AsyncEngine, None]:
    if request.config.getoption("--database") == "postgres":
        url = validated_postgres_url(os.environ.get("TEST_POSTGRES_URL"))
        # The generated schema is the only object created/dropped by this fixture.
        schema = f"stockflow_test_{uuid.uuid4().hex}"
        admin_engine = create_async_engine(url, poolclass=NullPool)
        test_engine = create_async_engine(
            url,
            pool_size=8,
            max_overflow=0,
            isolation_level="READ COMMITTED",
            connect_args={
                "server_settings": {
                    "search_path": schema,
                    "application_name": schema,
                    "statement_timeout": "15000",
                    "lock_timeout": "10000",
                }
            },
        )
        schema_created = False
        try:
            async with admin_engine.begin() as connection:
                await connection.execute(text(f'CREATE SCHEMA "{schema}"'))
                schema_created = True

            def migrate(connection: Connection) -> None:
                config = Config(
                    str(Path(__file__).resolve().parents[2] / "alembic.ini")
                )
                config.attributes["connection"] = connection
                command.upgrade(config, "head")

            async with test_engine.begin() as connection:
                await connection.run_sync(migrate)
            yield test_engine
        finally:
            await test_engine.dispose()
            if schema_created:
                async with admin_engine.begin() as connection:
                    await connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            await admin_engine.dispose()
        return

    test_engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(test_engine.sync_engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield test_engine
    finally:
        await test_engine.dispose()


@pytest_asyncio.fixture
async def db_session_factory(
    db_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False, autoflush=False)


@pytest_asyncio.fixture
async def client(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient, None]:

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with db_session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


RegisterUser = Callable[
    [AsyncClient, str, str], Coroutine[Any, Any, tuple[dict[str, Any], dict[str, str]]]
]


@pytest_asyncio.fixture
async def register_user() -> RegisterUser:
    async def _register(
        client: AsyncClient,
        email: str = "owner@example.com",
        organization: str = "Example Ltd",
    ) -> tuple[dict[str, Any], dict[str, str]]:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "organization_name": organization,
                "full_name": "Owner Example",
                "email": email,
                "password": "strong-password",
            },
        )
        assert response.status_code == 201, response.text
        data = response.json()
        return data, {"Authorization": f"Bearer {data['access_token']}"}

    return _register
