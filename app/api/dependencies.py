import uuid
from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.core.database import get_db
from app.core.observability import mark_span_error, traced_span
from app.core.security import decode_access_token
from app.models.user import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_PREFIX}/auth/token")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais",
        headers={"WWW-Authenticate": "Bearer"},
    )
    with traced_span("auth.authenticate") as auth_span:
        try:
            with traced_span("auth.jwt.decode"):
                payload = decode_access_token(token)
                user_id = uuid.UUID(payload["sub"])
                tenant_id = uuid.UUID(payload["tenant_id"])
        except (ValueError, KeyError, TypeError):
            auth_span.set_attribute("auth.result", "rejected")
            mark_span_error(auth_span, "invalid_credentials")
            raise credentials_error from None

        with traced_span(
            "auth.user.query",
            attributes={
                "db.operation.name": "SELECT",
                "db.collection.name": "users",
            },
        ):
            user = await db.scalar(
                select(User)
                .options(selectinload(User.tenant))
                .where(User.id == user_id, User.tenant_id == tenant_id)
            )
        if user is None:
            auth_span.set_attribute("auth.result", "rejected")
            mark_span_error(auth_span, "identity_not_found")
            raise credentials_error
        if not user.is_active:
            auth_span.set_attribute("auth.result", "rejected")
            mark_span_error(auth_span, "inactive_identity")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuário inativo",
            )
        auth_span.set_attribute("auth.result", "authenticated")
        return user


def require_roles(*allowed_roles: UserRole) -> Callable[..., Awaitable[User]]:
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        policy = ",".join(sorted(role.value for role in allowed_roles))
        with traced_span(
            "auth.rbac",
            attributes={"rbac.allowed_roles": policy},
        ) as rbac_span:
            if current_user.role not in allowed_roles:
                rbac_span.set_attribute("rbac.decision", "deny")
                mark_span_error(rbac_span, "rbac_denied")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Você não tem permissão para executar esta ação",
                )
            rbac_span.set_attribute("rbac.decision", "allow")
            return current_user

    return role_checker
