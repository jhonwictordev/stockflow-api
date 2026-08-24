import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import Field, model_validator

from app.models.sale import SaleStatus
from app.schemas.common import ORMModel, RequestModel


class SaleItemCreate(RequestModel):
    product_id: uuid.UUID
    quantity: int = Field(gt=0)


class SaleCreate(RequestModel):
    customer_name: str | None = Field(default=None, max_length=160)
    items: list[SaleItemCreate] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def products_must_be_unique(self) -> "SaleCreate":
        product_ids = [item.product_id for item in self.items]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("Cada produto deve aparecer apenas uma vez na venda")
        return self


class SaleItemRead(ORMModel):
    id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    sku: str
    quantity: int
    unit_price: Decimal
    subtotal: Decimal


class SaleRead(ORMModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    number: str
    created_by_id: uuid.UUID
    customer_name: str | None
    total: Decimal
    status: SaleStatus
    cancelled_at: datetime | None
    created_at: datetime
    updated_at: datetime
    items: list[SaleItemRead]
