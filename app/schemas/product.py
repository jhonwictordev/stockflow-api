import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import Field, computed_field, field_validator, model_validator

from app.models.stock import StockMovementType
from app.schemas.common import ORMModel, RequestModel


class ProductBase(RequestModel):
    name: str = Field(min_length=2, max_length=160)
    sku: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=500)
    price: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    minimum_stock: int = Field(default=0, ge=0)

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str) -> str:
        return value.strip().upper()


class ProductCreate(ProductBase):
    stock_quantity: int = Field(default=0, ge=0)


class ProductUpdate(RequestModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    sku: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=500)
    price: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    minimum_stock: int | None = Field(default=None, ge=0)
    is_active: bool | None = None

    @field_validator("sku")
    @classmethod
    def normalize_sku(cls, value: str | None) -> str | None:
        return value.strip().upper() if value is not None else None

    @model_validator(mode="after")
    def reject_empty_or_null_update(self) -> "ProductUpdate":
        if not self.model_fields_set:
            raise ValueError("Informe ao menos um campo para atualização")
        nonnullable = {"name", "sku", "price", "minimum_stock", "is_active"}
        if any(
            field in self.model_fields_set and getattr(self, field) is None
            for field in nonnullable
        ):
            raise ValueError("Este campo de produto não pode receber null")
        return self


class StockAdjustment(RequestModel):
    quantity: int = Field(
        description="Positive values add stock; negative values remove it"
    )
    reason: str = Field(min_length=3, max_length=200)

    @field_validator("quantity")
    @classmethod
    def quantity_cannot_be_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("A quantidade do ajuste não pode ser zero")
        return value


class ProductRead(ORMModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    sku: str
    description: str | None
    price: Decimal
    stock_quantity: int
    minimum_stock: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_low_stock(self) -> bool:
        return self.stock_quantity <= self.minimum_stock


class StockMovementRead(ORMModel):
    id: uuid.UUID
    product_id: uuid.UUID
    created_by_id: uuid.UUID
    movement_type: StockMovementType
    quantity_change: int
    balance_after: int
    reason: str
    reference_id: uuid.UUID | None
    created_at: datetime
