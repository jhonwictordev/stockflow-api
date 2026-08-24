import uuid
from datetime import datetime
from decimal import Decimal

from app.models.sale import SaleStatus
from app.schemas.common import ORMModel


class RecentSale(ORMModel):
    id: uuid.UUID
    number: str
    customer_name: str | None
    total: Decimal
    status: SaleStatus
    created_at: datetime


class DashboardSummary(ORMModel):
    active_products: int
    low_stock_products: int
    stock_units: int
    inventory_value: Decimal
    completed_sales: int
    sales_revenue: Decimal
    recent_sales: list[RecentSale]
