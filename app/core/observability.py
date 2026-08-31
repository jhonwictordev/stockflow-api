import logging
import re
import uuid
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass

from opentelemetry import metrics, propagate, trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import Counter, Histogram
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased
from opentelemetry.trace import Span, SpanKind, Status, StatusCode

from app.core.config import settings

logger = logging.getLogger(__name__)
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_safe_request_id = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{7,63}$")

tracer = trace.get_tracer("stockflow.application", settings.APP_VERSION)
meter = metrics.get_meter("stockflow.application", settings.APP_VERSION)

sales_completed: Counter = meter.create_counter(
    "stockflow.sales.completed",
    unit="1",
    description="Vendas concluídas com commit confirmado.",
)
sales_rollbacks: Counter = meter.create_counter(
    "stockflow.sales.rollbacks",
    unit="1",
    description="Transações de venda revertidas.",
)
sales_insufficient_stock: Counter = meter.create_counter(
    "stockflow.sales.insufficient_stock",
    unit="1",
    description="Tentativas de venda rejeitadas por estoque insuficiente.",
)
sales_transaction_duration: Histogram = meter.create_histogram(
    "stockflow.sales.transaction.duration",
    unit="s",
    description="Duração da transação de criação de venda.",
)


@dataclass
class ObservabilityRuntime:
    tracer_provider: TracerProvider
    meter_provider: MeterProvider


_runtime: ObservabilityRuntime | None = None


def configure_observability() -> None:
    """Configure OTLP exporters once; disabled environments keep no-op providers."""

    global _runtime
    if not settings.OTEL_ENABLED or _runtime is not None:
        return

    endpoint = settings.OTEL_EXPORTER_OTLP_ENDPOINT.rstrip("/")
    resource = Resource.create(
        {
            "service.name": settings.OTEL_SERVICE_NAME,
            "service.version": settings.APP_VERSION,
            "deployment.environment.name": settings.ENVIRONMENT,
        }
    )
    tracer_provider = TracerProvider(
        resource=resource,
        sampler=ParentBased(TraceIdRatioBased(settings.OTEL_TRACE_SAMPLE_RATIO)),
    )
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(
                endpoint=f"{endpoint}/v1/traces",
                timeout=settings.OTEL_EXPORT_TIMEOUT_SECONDS,
            )
        )
    )
    trace.set_tracer_provider(tracer_provider)

    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(
            endpoint=f"{endpoint}/v1/metrics",
            timeout=settings.OTEL_EXPORT_TIMEOUT_SECONDS,
        ),
        export_interval_millis=settings.OTEL_EXPORT_INTERVAL_MILLISECONDS,
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)
    _runtime = ObservabilityRuntime(tracer_provider, meter_provider)


def shutdown_observability() -> None:
    global _runtime
    if _runtime is None:
        return
    _runtime.meter_provider.shutdown()
    _runtime.tracer_provider.shutdown()
    _runtime = None


def normalize_request_id(value: str | None) -> str:
    if value and _safe_request_id.fullmatch(value):
        return value
    return str(uuid.uuid4())


def bind_request_id(request_id: str) -> Token[str | None]:
    return _request_id.set(request_id)


def reset_request_id(token: Token[str | None]) -> None:
    _request_id.reset(token)


def current_request_id() -> str | None:
    return _request_id.get()


def extract_trace_context(headers: Mapping[str, str]) -> Context:
    return propagate.extract(headers)


@contextmanager
def traced_span(
    name: str,
    *,
    attributes: Mapping[str, str | bool | int | float] | None = None,
    kind: SpanKind = SpanKind.INTERNAL,
    context: Context | None = None,
) -> Iterator[Span]:
    with tracer.start_as_current_span(
        name,
        context=context,
        kind=kind,
        record_exception=False,
        set_status_on_exception=False,
    ) as span:
        request_id = current_request_id()
        if request_id:
            span.set_attribute("request.id", request_id)
        if attributes:
            for key, value in attributes.items():
                span.set_attribute(key, value)
        yield span


def mark_span_error(span: Span, reason: str) -> None:
    span.set_attribute("error.type", reason)
    span.set_status(Status(StatusCode.ERROR, reason))


def record_sale_completed(duration_seconds: float) -> None:
    sales_completed.add(1)
    sales_transaction_duration.record(duration_seconds, {"outcome": "committed"})


def record_sale_rollback(duration_seconds: float) -> None:
    sales_rollbacks.add(1)
    sales_transaction_duration.record(duration_seconds, {"outcome": "rolled_back"})


def record_insufficient_stock() -> None:
    sales_insufficient_stock.add(1)


class RequestContextLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = current_request_id() or "background"
        span_context = trace.get_current_span().get_span_context()
        record.trace_id = (
            format(span_context.trace_id, "032x")
            if span_context.is_valid
            else "unavailable"
        )
        return True


def configure_logging_context() -> None:
    context_filter = RequestContextLogFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(context_filter)
