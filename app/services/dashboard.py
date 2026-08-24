import uuid
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Product
from app.models.sale import Sale, SaleStatus
from app.schemas.dashboard import DashboardSummary


async def get_dashboard_summary(
    db: AsyncSession, tenant_id: uuid.UUID
) -> DashboardSummary:
    product_metrics = (
        await db.execute(
            select(
                func.count(Product.id),
                func.coalesce(func.sum(Product.stock_quantity), 0),
                func.coalesce(
                    func.sum(
                        case(
                            (Product.stock_quantity <= Product.minimum_stock, 1),
                            else_=0,
                        )
                    ),
                    0,
                ),
                func.coalesce(func.sum(Product.price * Product.stock_quantity), 0),
            ).where(
                Product.tenant_id == tenant_id,
                Product.is_active.is_(True),
            )
        )
    ).one()

    sale_metrics = (
        await db.execute(
            select(
                func.count(Sale.id),
                func.coalesce(func.sum(Sale.total), 0),
            ).where(
                Sale.tenant_id == tenant_id,
                Sale.status == SaleStatus.COMPLETED,
            )
        )
    ).one()

    recent_sales = list(
        await db.scalars(
            select(Sale)
            .where(Sale.tenant_id == tenant_id)
            .order_by(Sale.created_at.desc())
            .limit(5)
        )
    )

    return DashboardSummary(
        active_products=int(product_metrics[0] or 0),
        stock_units=int(product_metrics[1] or 0),
        low_stock_products=int(product_metrics[2] or 0),
        inventory_value=Decimal(product_metrics[3] or 0),
        completed_sales=int(sale_metrics[0] or 0),
        sales_revenue=Decimal(sale_metrics[1] or 0),
        recent_sales=recent_sales,
    )
