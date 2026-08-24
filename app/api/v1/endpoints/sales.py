import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_roles
from app.core.database import get_db
from app.models.sale import Sale, SaleStatus
from app.models.user import User, UserRole
from app.schemas.common import Page
from app.schemas.sale import SaleCreate, SaleRead
from app.services import sales as sale_service

router = APIRouter(prefix="/sales", tags=["Vendas"])
sale_creator = require_roles(
    UserRole.OWNER,
    UserRole.ADMIN,
    UserRole.MANAGER,
    UserRole.SALESPERSON,
)
sale_manager = require_roles(UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER)


@router.post(
    "",
    response_model=SaleRead,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar uma venda",
)
async def create_sale(
    data: SaleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(sale_creator),
) -> Sale:
    return await sale_service.create_sale(db, current_user, data)


@router.get("", response_model=Page[SaleRead], summary="Listar vendas")
async def list_sales(
    sale_status: SaleStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Page[SaleRead]:
    sales, total = await sale_service.list_sales(
        db,
        current_user.tenant_id,
        status=sale_status,
        limit=limit,
        offset=offset,
    )
    return Page(items=sales, total=total, limit=limit, offset=offset)


@router.get("/{sale_id}", response_model=SaleRead, summary="Consultar uma venda")
async def get_sale(
    sale_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Sale:
    return await sale_service.get_sale(db, current_user.tenant_id, sale_id)


@router.post("/{sale_id}/cancel", response_model=SaleRead, summary="Cancelar uma venda")
async def cancel_sale(
    sale_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(sale_manager),
) -> Sale:
    return await sale_service.cancel_sale(db, current_user, sale_id)
