import uuid
from collections.abc import Iterator

import pytest
from httpx import AsyncClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core import observability
from app.models.product import Product
from app.models.sale import Sale, SaleItem
from app.models.stock import StockMovement, StockMovementType
from app.tests.conftest import RegisterUser
from app.tests.postgres_support import contend, write_evidence
from app.tests.test_inventory_sales import create_product
from app.tests.test_observability import RecordingInstrument

pytestmark = pytest.mark.postgres


@pytest.fixture
def trace_capture(monkeypatch: pytest.MonkeyPatch) -> Iterator[InMemorySpanExporter]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(observability, "tracer", provider.get_tracer("stockflow.tests"))
    try:
        yield exporter
    finally:
        provider.shutdown()


@pytest.mark.parametrize("repetition", range(5))
async def test_two_purchases_compete_for_last_item(
    repetition: int,
    client: AsyncClient,
    register_user: RegisterUser,
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    trace_capture: InMemorySpanExporter,
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> None:
    _, headers = await register_user(client)
    product = await create_product(client, headers, stock=1)
    product_id = uuid.UUID(product["id"])
    payload = {"items": [{"product_id": product["id"], "quantity": 1}]}
    completed, rollbacks, insufficient = (RecordingInstrument() for _ in range(3))
    monkeypatch.setattr(observability, "sales_completed", completed)
    monkeypatch.setattr(observability, "sales_rollbacks", rollbacks)
    monkeypatch.setattr(observability, "sales_insufficient_stock", insufficient)
    trace_capture.clear()

    responses, blocked = await contend(
        db_engine,
        db_session_factory,
        select(Product).where(Product.id == product_id).with_for_update(),
        [
            lambda: client.post(
                "/api/v1/sales",
                json=payload,
                headers={**headers, "X-Request-ID": "demo-purchase-a"},
            ),
            lambda: client.post(
                "/api/v1/sales",
                json=payload,
                headers={**headers, "X-Request-ID": "demo-purchase-b"},
            ),
        ],
    )
    assert sorted(r.status_code for r in responses) == [201, 422]
    assert completed.calls == rollbacks.calls == insufficient.calls == [(1, None)]
    async with db_session_factory() as db:
        assert await db.scalar(select(Product.stock_quantity)) == 0
        assert await db.scalar(select(func.count()).select_from(Sale)) == 1
        assert await db.scalar(select(func.count()).select_from(SaleItem)) == 1
        assert await db.scalar(select(func.count()).select_from(StockMovement)) == 2
        movement = await db.scalar(
            select(StockMovement).where(
                StockMovement.movement_type == StockMovementType.SALE
            )
        )
        assert movement.quantity_change == -1
        assert movement.balance_after == 0
        assert await db.scalar(text("SHOW transaction_isolation")) == "read committed"
        version = await db.scalar(text("SHOW server_version"))
        assert await db.scalar(text("SELECT version_num FROM alembic_version"))

    spans = trace_capture.get_finished_spans()
    assert sum(s.name == "sales.transaction.commit" for s in spans) == 1
    assert sum(s.name == "sales.transaction.rollback" for s in spans) == 1
    if repetition == 0 and (directory := request.config.getoption("--evidence-dir")):
        write_evidence(directory, responses, spans, blocked, version)


async def test_opposite_item_order_does_not_deadlock(
    client: AsyncClient,
    register_user: RegisterUser,
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, headers = await register_user(client)
    first = await create_product(client, headers, sku="FIRST", stock=2)
    second = await create_product(client, headers, sku="SECOND", stock=2)
    items = [{"product_id": p["id"], "quantity": 1} for p in (first, second)]
    responses, _ = await contend(
        db_engine,
        db_session_factory,
        select(Product).order_by(Product.id).with_for_update(),
        [
            lambda: client.post(
                "/api/v1/sales", headers=headers, json={"items": items}
            ),
            lambda: client.post(
                "/api/v1/sales", headers=headers, json={"items": items[::-1]}
            ),
        ],
    )
    assert [r.status_code for r in responses] == [201, 201]
    async with db_session_factory() as db:
        assert list(await db.scalars(select(Product.stock_quantity))) == [0, 0]
        assert await db.scalar(select(func.count()).select_from(Sale)) == 2
        assert await db.scalar(select(func.count()).select_from(SaleItem)) == 4
        assert (
            await db.scalar(
                select(func.count())
                .select_from(StockMovement)
                .where(StockMovement.movement_type == StockMovementType.SALE)
            )
            == 4
        )


async def test_concurrent_cancellation_restores_stock_only_once(
    client: AsyncClient,
    register_user: RegisterUser,
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    _, headers = await register_user(client)
    product = await create_product(client, headers, stock=1)
    sale = await client.post(
        "/api/v1/sales",
        headers=headers,
        json={"items": [{"product_id": product["id"], "quantity": 1}]},
    )
    assert sale.status_code == 201
    sale_id = uuid.UUID(sale.json()["id"])
    responses, _ = await contend(
        db_engine,
        db_session_factory,
        select(Sale).where(Sale.id == sale_id).with_for_update(),
        [lambda: client.post(f"/api/v1/sales/{sale_id}/cancel", headers=headers)] * 2,
    )
    assert sorted(r.status_code for r in responses) == [200, 409]
    async with db_session_factory() as db:
        assert await db.scalar(select(Product.stock_quantity)) == 1
        assert (
            await db.scalar(
                select(func.count())
                .select_from(StockMovement)
                .where(
                    StockMovement.movement_type == StockMovementType.SALE_CANCELLATION
                )
            )
            == 1
        )


async def test_rollback_releases_locks_for_queued_purchase(
    client: AsyncClient,
    register_user: RegisterUser,
    db_engine: AsyncEngine,
    db_session_factory: async_sessionmaker[AsyncSession],
    trace_capture: InMemorySpanExporter,
) -> None:
    _, headers = await register_user(client)
    first = await create_product(client, headers, sku="AVAILABLE", stock=2)
    second = await create_product(client, headers, sku="EMPTY", stock=0)
    good_items = [{"product_id": first["id"], "quantity": 1}]
    bad_items = good_items + [{"product_id": second["id"], "quantity": 1}]
    responses, _ = await contend(
        db_engine,
        db_session_factory,
        select(Product).where(Product.id == uuid.UUID(first["id"])).with_for_update(),
        [
            lambda: client.post(
                "/api/v1/sales", headers=headers, json={"items": bad_items}
            ),
            lambda: client.post(
                "/api/v1/sales", headers=headers, json={"items": good_items}
            ),
        ],
        queue_first=True,
    )
    assert [r.status_code for r in responses] == [422, 201]
    spans = trace_capture.get_finished_spans()
    rollback = next(s for s in spans if s.name == "sales.transaction.rollback")
    commit = next(s for s in spans if s.name == "sales.transaction.commit")
    assert rollback.end_time <= commit.start_time
    async with db_session_factory() as db:
        assert (
            await db.scalar(
                select(Product.stock_quantity).where(
                    Product.id == uuid.UUID(first["id"])
                )
            )
            == 1
        )
        assert await db.scalar(select(func.count()).select_from(Sale)) == 1
        assert await db.scalar(select(func.count()).select_from(SaleItem)) == 1
        assert (
            await db.scalar(
                select(func.count())
                .select_from(StockMovement)
                .where(StockMovement.movement_type == StockMovementType.SALE)
            )
            == 1
        )
