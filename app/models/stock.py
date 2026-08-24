import uuid
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.product import Product


class StockMovementType(StrEnum):
    INITIAL = "initial"
    ADJUSTMENT = "adjustment"
    SALE = "sale"
    SALE_CANCELLATION = "sale_cancellation"


class StockMovement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint("quantity_change != 0", name="nonzero_quantity_change"),
        CheckConstraint("balance_after >= 0", name="nonnegative_balance"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True, nullable=False
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    created_by_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    movement_type: Mapped[StockMovementType] = mapped_column(
        Enum(StockMovementType, native_enum=False, length=24), nullable=False
    )
    quantity_change: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(String(200), nullable=False)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True, index=True)

    product: Mapped["Product"] = relationship(back_populates="stock_movements")
