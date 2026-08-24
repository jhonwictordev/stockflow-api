import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_roles
from app.core.database import get_db
from app.models.product import Product
from app.models.user import User, UserRole
from app.schemas.common import Page
from app.schemas.product import (
    ProductCreate,
    ProductRead,
    ProductUpdate,
    StockAdjustment,
    StockMovementRead,
)
from app.services import products as product_service

router = APIRouter(prefix="/products", tags=["Produtos"])
product_editor = require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER)
product_admin = require_roles(UserRole.OWNER, UserRole.ADMIN)


@router.post(
    "",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar um produto",
)
async def create_product(
    data: ProductCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(product_editor),
) -> Product:
    return await product_service.create_product(db, current_user, data)


@router.get("", response_model=Page[ProductRead], summary="Listar produtos")
async def list_products(
    search: str | None = Query(default=None, max_length=100),
    low_stock: bool = False,
    include_inactive: bool = False,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Page[ProductRead]:
    products, total = await product_service.list_products(
        db,
        current_user.tenant_id,
        search=search,
        low_stock=low_stock,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )
    return Page(items=products, total=total, limit=limit, offset=offset)


@router.get("/{product_id}", response_model=ProductRead, summary="Consultar um produto")
async def get_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Product:
    return await product_service.get_product(db, current_user.tenant_id, product_id)


@router.patch(
    "/{product_id}", response_model=ProductRead, summary="Atualizar um produto"
)
async def update_product(
    product_id: uuid.UUID,
    data: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(product_editor),
) -> Product:
    return await product_service.update_product(
        db, current_user.tenant_id, product_id, data
    )


@router.post(
    "/{product_id}/stock-adjustments",
    response_model=ProductRead,
    summary="Registrar um ajuste de estoque",
)
async def adjust_stock(
    product_id: uuid.UUID,
    data: StockAdjustment,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(product_editor),
) -> Product:
    return await product_service.adjust_stock(db, current_user, product_id, data)


@router.get(
    "/{product_id}/stock-movements",
    response_model=Page[StockMovementRead],
    summary="Listar movimentações de estoque",
)
async def list_stock_movements(
    product_id: uuid.UUID,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Page[StockMovementRead]:
    movements, total = await product_service.list_stock_movements(
        db,
        current_user.tenant_id,
        product_id,
        limit=limit,
        offset=offset,
    )
    return Page(items=movements, total=total, limit=limit, offset=offset)


@router.delete(
    "/{product_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Desativar um produto",
)
async def deactivate_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(product_admin),
) -> Response:
    await product_service.deactivate_product(db, current_user.tenant_id, product_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
