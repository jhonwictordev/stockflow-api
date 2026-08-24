import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, InsufficientStockError, NotFoundError
from app.models.product import Product
from app.models.sale import Sale, SaleItem, SaleStatus
from app.models.stock import StockMovement, StockMovementType
from app.models.user import User
from app.schemas.sale import SaleCreate

MONEY = Decimal("0.01")


async def create_sale(db: AsyncSession, actor: User, data: SaleCreate) -> Sale:
    requested_ids = [item.product_id for item in data.items]
    result = await db.scalars(
        select(Product)
        .where(
            Product.tenant_id == actor.tenant_id,
            Product.id.in_(requested_ids),
            Product.is_active.is_(True),
        )
        .order_by(Product.id)
        .with_for_update()
    )
    products = {product.id: product for product in result}
    if len(products) != len(requested_ids):
        raise NotFoundError("Um ou mais produtos não existem ou estão inativos")

    sale = Sale(
        tenant_id=actor.tenant_id,
        number=f"VEN-{datetime.now(UTC):%Y%m%d}-{uuid.uuid4().hex[:8].upper()}",
        created_by_id=actor.id,
        customer_name=data.customer_name.strip() if data.customer_name else None,
        total=Decimal("0.00"),
        status=SaleStatus.COMPLETED,
        items=[],
    )
    db.add(sale)
    await db.flush()

    total = Decimal("0.00")
    for requested_item in data.items:
        product = products[requested_item.product_id]
        if product.stock_quantity < requested_item.quantity:
            product_sku = product.sku
            await db.rollback()
            raise InsufficientStockError(
                f"Estoque insuficiente para o produto {product_sku}"
            )
        product.stock_quantity -= requested_item.quantity
        subtotal = (product.price * requested_item.quantity).quantize(
            MONEY, rounding=ROUND_HALF_UP
        )
        total += subtotal
        sale.items.append(
            SaleItem(
                product_id=product.id,
                product_name=product.name,
                sku=product.sku,
                quantity=requested_item.quantity,
                unit_price=product.price,
                subtotal=subtotal,
            )
        )
        db.add(
            StockMovement(
                tenant_id=actor.tenant_id,
                product_id=product.id,
                created_by_id=actor.id,
                movement_type=StockMovementType.SALE,
                quantity_change=-requested_item.quantity,
                balance_after=product.stock_quantity,
                reason=f"Venda {sale.number}",
                reference_id=sale.id,
            )
        )

    sale.total = total.quantize(MONEY, rounding=ROUND_HALF_UP)
    await db.commit()
    return await get_sale(db, actor.tenant_id, sale.id)


async def get_sale(db: AsyncSession, tenant_id: uuid.UUID, sale_id: uuid.UUID) -> Sale:
    sale = await db.scalar(
        select(Sale)
        .options(selectinload(Sale.items))
        .where(Sale.id == sale_id, Sale.tenant_id == tenant_id)
    )
    if sale is None:
        raise NotFoundError("Venda não encontrada")
    return sale


async def list_sales(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    status: SaleStatus | None,
    limit: int,
    offset: int,
) -> tuple[list[Sale], int]:
    conditions = [Sale.tenant_id == tenant_id]
    if status is not None:
        conditions.append(Sale.status == status)
    total = await db.scalar(select(func.count(Sale.id)).where(*conditions))
    result = await db.scalars(
        select(Sale)
        .options(selectinload(Sale.items))
        .where(*conditions)
        .order_by(Sale.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(result.unique()), int(total or 0)


async def cancel_sale(db: AsyncSession, actor: User, sale_id: uuid.UUID) -> Sale:
    sale = await db.scalar(
        select(Sale)
        .options(selectinload(Sale.items))
        .where(Sale.id == sale_id, Sale.tenant_id == actor.tenant_id)
        .with_for_update()
    )
    if sale is None:
        raise NotFoundError("Venda não encontrada")
    if sale.status is SaleStatus.CANCELLED:
        raise ConflictError("A venda já está cancelada")

    product_ids = [item.product_id for item in sale.items]
    result = await db.scalars(
        select(Product)
        .where(Product.tenant_id == actor.tenant_id, Product.id.in_(product_ids))
        .order_by(Product.id)
        .with_for_update()
    )
    products = {product.id: product for product in result}
    if len(products) != len(product_ids):
        raise ConflictError("Não foi possível restaurar o estoque da venda")

    for item in sale.items:
        product = products[item.product_id]
        product.stock_quantity += item.quantity
        db.add(
            StockMovement(
                tenant_id=actor.tenant_id,
                product_id=product.id,
                created_by_id=actor.id,
                movement_type=StockMovementType.SALE_CANCELLATION,
                quantity_change=item.quantity,
                balance_after=product.stock_quantity,
                reason=f"Cancelamento da venda {sale.number}",
                reference_id=sale.id,
            )
        )
    sale.status = SaleStatus.CANCELLED
    sale.cancelled_at = datetime.now(UTC)
    await db.commit()
    return await get_sale(db, actor.tenant_id, sale.id)
