import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.security import get_password_hash
from app.models.user import User, UserRole
from app.schemas.user import UserCreate, UserUpdate

ROLE_LEVEL = {
    UserRole.VIEWER: 1,
    UserRole.SALESPERSON: 2,
    UserRole.MANAGER: 3,
    UserRole.ADMIN: 4,
    UserRole.OWNER: 5,
}


def _can_assign(actor: User, role: UserRole) -> bool:
    return role is not UserRole.OWNER and ROLE_LEVEL[actor.role] > ROLE_LEVEL[role]


async def create_user(db: AsyncSession, actor: User, data: UserCreate) -> User:
    if not _can_assign(actor, data.role):
        raise ForbiddenError("Você não pode atribuir esta função")

    email = data.email.lower()
    if await db.scalar(select(User.id).where(User.email == email)):
        raise ConflictError("Já existe um usuário com este e-mail")

    user = User(
        tenant_id=actor.tenant_id,
        email=email,
        full_name=data.full_name.strip(),
        hashed_password=get_password_hash(data.password),
        role=data.role,
        is_active=True,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Já existe um usuário com este e-mail") from exc
    await db.refresh(user)
    return user


async def get_user(db: AsyncSession, tenant_id: uuid.UUID, user_id: uuid.UUID) -> User:
    user = await db.scalar(
        select(User).where(User.id == user_id, User.tenant_id == tenant_id)
    )
    if user is None:
        raise NotFoundError("Usuário não encontrado")
    return user


async def list_users(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
) -> tuple[list[User], int]:
    conditions = (User.tenant_id == tenant_id,)
    total = await db.scalar(select(func.count(User.id)).where(*conditions))
    result = await db.scalars(
        select(User)
        .where(*conditions)
        .order_by(User.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result), int(total or 0)


async def update_user(
    db: AsyncSession,
    actor: User,
    user_id: uuid.UUID,
    data: UserUpdate,
) -> User:
    target = await get_user(db, actor.tenant_id, user_id)
    if target.role is UserRole.OWNER:
        raise ForbiddenError("O proprietário da organização não pode ser alterado")
    if ROLE_LEVEL[actor.role] <= ROLE_LEVEL[target.role]:
        raise ForbiddenError("Você não pode alterar este usuário")
    if data.role is not None and not _can_assign(actor, data.role):
        raise ForbiddenError("Você não pode atribuir esta função")
    if actor.id == target.id and data.is_active is False:
        raise ForbiddenError("Você não pode desativar o próprio usuário")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(target, field, value)
    await db.commit()
    await db.refresh(target)
    return target
