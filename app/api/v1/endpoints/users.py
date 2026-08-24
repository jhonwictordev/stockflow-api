import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_roles
from app.core.database import get_db
from app.models.user import User, UserRole
from app.schemas.common import Page
from app.schemas.user import UserCreate, UserRead, UserUpdate
from app.services import users as user_service

router = APIRouter(prefix="/users", tags=["Usuários"])
admin_user = require_roles(UserRole.OWNER, UserRole.ADMIN)


@router.post(
    "",
    response_model=UserRead,
    status_code=status.HTTP_201_CREATED,
    summary="Criar um usuário",
)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(admin_user),
) -> User:
    return await user_service.create_user(db, current_user, data)


@router.get("", response_model=Page[UserRead], summary="Listar usuários")
async def list_users(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(admin_user),
) -> Page[UserRead]:
    users, total = await user_service.list_users(
        db, current_user.tenant_id, limit=limit, offset=offset
    )
    return Page(items=users, total=total, limit=limit, offset=offset)


@router.get("/{user_id}", response_model=UserRead, summary="Consultar um usuário")
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(admin_user),
) -> User:
    return await user_service.get_user(db, current_user.tenant_id, user_id)


@router.patch("/{user_id}", response_model=UserRead, summary="Atualizar um usuário")
async def update_user(
    user_id: uuid.UUID,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(admin_user),
) -> User:
    return await user_service.update_user(db, current_user, user_id, data)
