from collections.abc import AsyncGenerator, Callable, Coroutine
from typing import Any

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import get_db
from app.main import app
from app.models import Base

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
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

    session_factory = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client

    app.dependency_overrides.clear()
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
    await test_engine.dispose()


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
