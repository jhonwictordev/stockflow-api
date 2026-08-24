from datetime import UTC, datetime, timedelta

import jwt
import pytest
from httpx import AsyncClient

from app.core.config import settings
from app.core.security import create_access_token, decode_access_token
from app.tests.conftest import RegisterUser


async def test_register_login_and_read_profile(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    registration, headers = await register_user(client)

    assert registration["user"]["role"] == "owner"
    assert registration["user"]["email"] == "owner@example.com"

    login = await client.post(
        "/api/v1/auth/token",
        data={"username": "OWNER@EXAMPLE.COM", "password": "strong-password"},
    )
    assert login.status_code == 200
    assert login.json()["token_type"] == "bearer"
    assert login.headers["cache-control"] == "no-store"

    profile = await client.get("/api/v1/auth/me", headers=headers)
    assert profile.status_code == 200
    assert profile.json()["tenant"]["name"] == "Example Ltd"


async def test_rejects_duplicate_email_and_invalid_password(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    await register_user(client)
    duplicate = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Another Ltd",
            "full_name": "Other Owner",
            "email": "OWNER@example.com",
            "password": "another-password",
        },
    )
    assert duplicate.status_code == 409

    login = await client.post(
        "/api/v1/auth/token",
        data={"username": "owner@example.com", "password": "wrong-password"},
    )
    assert login.status_code == 401
    assert login.headers["www-authenticate"] == "Bearer"


async def test_protected_endpoint_requires_bearer_token(client: AsyncClient) -> None:
    response = await client.get("/api/v1/products")
    assert response.status_code == 401


async def test_registration_rejects_a_weak_password(client: AsyncClient) -> None:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Weak Password Ltd",
            "full_name": "Weak Password Owner",
            "email": "weak@example.com",
            "password": "123456789012",
        },
    )

    assert response.status_code == 422


async def test_expired_access_token_is_rejected(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    registration, _ = await register_user(client)
    user = registration["user"]
    expired_token = create_access_token(
        user["id"],
        tenant_id=user["tenant_id"],
        role=user["role"],
        expires_delta=timedelta(seconds=-1),
    )

    response = await client.get(
        "/api/v1/products",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert response.status_code == 401


def test_access_token_requires_role_claim() -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "73d76ecb-0a32-4efc-8c42-131e65b21b07",
            "tenant_id": "671d6d9c-a35e-42cf-8bc4-24aaf8d04f53",
            "iss": settings.JWT_ISSUER,
            "aud": settings.JWT_AUDIENCE,
            "iat": now,
            "exp": now + timedelta(minutes=5),
            "type": "access",
        },
        settings.SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )

    with pytest.raises(ValueError, match="Token inválido"):
        decode_access_token(token)
