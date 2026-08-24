import re
import unicodedata
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.security import get_password_hash, verify_password
from app.models.user import Tenant, User, UserRole
from app.schemas.auth import RegisterRequest


def _slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized.lower()).strip("-")
    return slug[:60] or "organization"


async def register_tenant(db: AsyncSession, data: RegisterRequest) -> User:
    email = data.email.lower()
    if await db.scalar(select(User.id).where(User.email == email)):
        raise ConflictError("Já existe um usuário com este e-mail")

    base_slug = _slugify(data.organization_name)
    slug = base_slug
    if await db.scalar(select(Tenant.id).where(Tenant.slug == slug)):
        slug = f"{base_slug}-{uuid.uuid4().hex[:6]}"

    tenant = Tenant(name=data.organization_name.strip(), slug=slug)
    db.add(tenant)
    await db.flush()

    user = User(
        tenant_id=tenant.id,
        email=email,
        full_name=data.full_name.strip(),
        hashed_password=get_password_hash(data.password),
        role=UserRole.OWNER,
        is_active=True,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("E-mail ou organização já cadastrados") from exc
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    user = await db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user
