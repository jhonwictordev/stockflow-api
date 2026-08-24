import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, InsufficientStockError, NotFoundError
from app.models.product import Product
from app.models.stock import StockMovement, StockMovementType
from app.models.user import User
from app.schemas.product import ProductCreate, ProductUpdate, StockAdjustment


async def create_product(db: AsyncSession, actor: User, data: ProductCreate) -> Product:
    product = Product(tenant_id=actor.tenant_id, **data.model_dump())
    db.add(product)
    try:
        await db.flush()
        if product.stock_quantity:
            db.add(
                StockMovement(
                    tenant_id=actor.tenant_id,
                    product_id=product.id,
                    created_by_id=actor.id,
                    movement_type=StockMovementType.INITIAL,
                    quantity_change=product.stock_quantity,
                    balance_after=product.stock_quantity,
                    reason="Estoque inicial",
                )
            )
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Já existe um produto com este SKU") from exc
    await db.refresh(product)
    return product


async def get_product(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
) -> Product:
    product = await db.scalar(
        select(Product).where(
            Product.id == product_id,
            Product.tenant_id == tenant_id,
        )
    )
    if product is None:
        raise NotFoundError("Produto não encontrado")
    return product


async def list_products(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    search: str | None,
    low_stock: bool,
    include_inactive: bool,
    limit: int,
    offset: int,
) -> tuple[list[Product], int]:
    conditions = [Product.tenant_id == tenant_id]
    if not include_inactive:
        conditions.append(Product.is_active.is_(True))
    if low_stock:
        conditions.append(Product.stock_quantity <= Product.minimum_stock)
    if search:
        term = f"%{search.strip()}%"
        conditions.append(or_(Product.name.ilike(term), Product.sku.ilike(term)))

    total = await db.scalar(select(func.count(Product.id)).where(*conditions))
    result = await db.scalars(
        select(Product)
        .where(*conditions)
        .order_by(Product.name)
        .limit(limit)
        .offset(offset)
    )
    return list(result), int(total or 0)


async def update_product(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    data: ProductUpdate,
) -> Product:
    product = await get_product(db, tenant_id, product_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Já existe um produto com este SKU") from exc
    await db.refresh(product)
    return product


async def adjust_stock(
    db: AsyncSession,
    actor: User,
    product_id: uuid.UUID,
    data: StockAdjustment,
) -> Product:
    product = await db.scalar(
        select(Product)
        .where(Product.id == product_id, Product.tenant_id == actor.tenant_id)
        .with_for_update()
    )
    if product is None:
        raise NotFoundError("Produto não encontrado")
    new_quantity = product.stock_quantity + data.quantity
    if new_quantity < 0:
        raise InsufficientStockError("O ajuste deixaria o estoque negativo")
    product.stock_quantity = new_quantity
    db.add(
        StockMovement(
            tenant_id=actor.tenant_id,
            product_id=product.id,
            created_by_id=actor.id,
            movement_type=StockMovementType.ADJUSTMENT,
            quantity_change=data.quantity,
            balance_after=new_quantity,
            reason=data.reason.strip(),
        )
    )
    await db.commit()
    await db.refresh(product)
    return product


async def list_stock_movements(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    product_id: uuid.UUID,
    *,
    limit: int,
    offset: int,
) -> tuple[list[StockMovement], int]:
    await get_product(db, tenant_id, product_id)
    conditions = (
        StockMovement.tenant_id == tenant_id,
        StockMovement.product_id == product_id,
    )
    total = await db.scalar(select(func.count(StockMovement.id)).where(*conditions))
    result = await db.scalars(
        select(StockMovement)
        .where(*conditions)
        .order_by(StockMovement.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result), int(total or 0)


async def deactivate_product(
    db: AsyncSession, tenant_id: uuid.UUID, product_id: uuid.UUID
) -> None:
    product = await get_product(db, tenant_id, product_id)
    product.is_active = False
    await db.commit()
