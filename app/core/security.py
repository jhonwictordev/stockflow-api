import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import jwt
from jwt import InvalidTokenError
from passlib.context import CryptContext

from app.core.config import settings

password_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
DUMMY_PASSWORD_HASH = password_context.hash(secrets.token_urlsafe(32))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return cast(bool, password_context.verify(plain_password, hashed_password))


def get_password_hash(password: str) -> str:
    return cast(str, password_context.hash(password))


def create_access_token(
    subject: str,
    *,
    tenant_id: str,
    role: str,
    expires_delta: timedelta | None = None,
) -> str:
    now = datetime.now(UTC)
    expires_at = now + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload = {
        "sub": subject,
        "tenant_id": tenant_id,
        "role": role,
        "iss": settings.JWT_ISSUER,
        "aud": settings.JWT_AUDIENCE,
        "iat": now,
        "exp": expires_at,
        "type": "access",
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            audience=settings.JWT_AUDIENCE,
            issuer=settings.JWT_ISSUER,
            options={
                "require": [
                    "sub",
                    "tenant_id",
                    "role",
                    "iss",
                    "aud",
                    "iat",
                    "exp",
                    "type",
                ]
            },
        )
    except InvalidTokenError as exc:
        raise ValueError("Token inválido ou expirado") from exc

    if payload.get("type") != "access" or not payload.get("sub"):
        raise ValueError("Token inválido")
    return payload
