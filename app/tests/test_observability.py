import uuid
from dataclasses import dataclass, field

import pytest
from httpx import AsyncClient
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from app.core import observability
from app.tests.conftest import RegisterUser
from app.tests.test_inventory_sales import create_product


@dataclass
class RecordingInstrument:
    calls: list[tuple[float, dict[str, str] | None]] = field(default_factory=list)

    def add(
        self,
        value: float,
        attributes: dict[str, str] | None = None,
    ) -> None:
        self.calls.append((value, attributes))

    def record(
        self,
        value: float,
        attributes: dict[str, str] | None = None,
    ) -> None:
        self.calls.append((value, attributes))


async def test_sale_trace_reaches_commit_and_correlates_request_id(
    client: AsyncClient,
    register_user: RegisterUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(
        observability,
        "tracer",
        provider.get_tracer("stockflow.tests"),
    )

    registration, headers = await register_user(client)
    product = await create_product(client, headers)
    exporter.clear()

    request_id = "sale-request-20260831"
    response = await client.post(
        "/api/v1/sales",
        headers={**headers, "X-Request-ID": request_id},
        json={
            "customer_name": "Pessoa que não pode aparecer no trace",
            "items": [{"product_id": product["id"], "quantity": 2}],
        },
    )

    assert response.status_code == 201, response.text
    assert response.headers["x-request-id"] == request_id

    spans = exporter.get_finished_spans()
    spans_by_name = {span.name: span for span in spans}
    expected_spans = {
        "POST /api/v1/sales",
        "auth.authenticate",
        "auth.jwt.decode",
        "auth.user.query",
        "auth.rbac",
        "sales.transaction",
        "sales.products.query",
        "sales.stock.lock",
        "sales.persist",
        "sales.transaction.commit",
        "sales.detail.query",
    }
    assert expected_spans <= spans_by_name.keys()

    request_span = spans_by_name["POST /api/v1/sales"]
    transaction_span = spans_by_name["sales.transaction"]
    query_span = spans_by_name["sales.products.query"]
    lock_span = spans_by_name["sales.stock.lock"]
    commit_span = spans_by_name["sales.transaction.commit"]
    assert transaction_span.parent is not None
    assert transaction_span.parent.span_id == request_span.context.span_id
    assert query_span.parent is not None
    assert query_span.parent.span_id == transaction_span.context.span_id
    assert lock_span.parent is not None
    assert lock_span.parent.span_id == query_span.context.span_id
    assert commit_span.parent is not None
    assert commit_span.parent.span_id == transaction_span.context.span_id

    sensitive_values = {
        registration["user"]["id"],
        registration["user"]["tenant_id"],
        product["id"],
        "Pessoa que não pode aparecer no trace",
    }
    for span in spans:
        assert span.attributes is not None
        assert span.attributes.get("request.id") == request_id
        serialized_attributes = " ".join(
            f"{key}={value}" for key, value in span.attributes.items()
        )
        assert all(value not in serialized_attributes for value in sensitive_values)

    provider.shutdown()


async def test_sale_metrics_have_bounded_non_sensitive_dimensions(
    client: AsyncClient,
    register_user: RegisterUser,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    completed = RecordingInstrument()
    rollbacks = RecordingInstrument()
    insufficient = RecordingInstrument()
    duration = RecordingInstrument()
    monkeypatch.setattr(observability, "sales_completed", completed)
    monkeypatch.setattr(observability, "sales_rollbacks", rollbacks)
    monkeypatch.setattr(observability, "sales_insufficient_stock", insufficient)
    monkeypatch.setattr(observability, "sales_transaction_duration", duration)

    _, headers = await register_user(client)
    product = await create_product(client, headers, stock=1)

    successful = await client.post(
        "/api/v1/sales",
        headers=headers,
        json={"items": [{"product_id": product["id"], "quantity": 1}]},
    )
    rejected = await client.post(
        "/api/v1/sales",
        headers=headers,
        json={"items": [{"product_id": product["id"], "quantity": 1}]},
    )

    assert successful.status_code == 201
    assert rejected.status_code == 422
    assert completed.calls == [(1, None)]
    assert rollbacks.calls == [(1, None)]
    assert insufficient.calls == [(1, None)]
    assert len(duration.calls) == 2
    duration_outcomes = {
        attributes["outcome"] for _, attributes in duration.calls if attributes
    }
    assert duration_outcomes == {
        "committed",
        "rolled_back",
    }
    assert all(
        attributes is None or set(attributes) == {"outcome"}
        for _, attributes in (
            completed.calls + rollbacks.calls + insufficient.calls + duration.calls
        )
    )


async def test_request_id_rejects_values_that_could_contain_personal_data(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/health",
        headers={"X-Request-ID": "person@example.com"},
    )

    generated_request_id = response.headers["x-request-id"]
    assert generated_request_id != "person@example.com"
    assert str(uuid.UUID(generated_request_id)) == generated_request_id
