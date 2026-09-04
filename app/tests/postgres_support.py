"""Real lock contention helpers. Never monkeypatch the transaction under test."""

import asyncio
import json
import os
from collections.abc import Callable, Coroutine, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from httpx import Response
from opentelemetry.sdk.trace import ReadableSpan
from sqlalchemy import Select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


async def wait_for_two_blocked_connections(engine: AsyncEngine) -> int:
    async with engine.connect() as connection:
        connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
        async with asyncio.timeout(6):
            while True:
                blocked = list(
                    await connection.scalars(
                        text(
                            "SELECT pid FROM pg_stat_activity "
                            "WHERE application_name = "
                            "current_setting('application_name') "
                            "AND pid <> pg_backend_pid() AND wait_event_type = 'Lock' "
                            "AND cardinality(pg_blocking_pids(pid)) > 0 "
                            "AND position('FOR UPDATE' in query) > 0"
                        )
                    )
                )
                if len(set(blocked)) == 2:
                    return 2
                await asyncio.sleep(0.02)


async def contend(
    engine: AsyncEngine,
    sessions: async_sessionmaker[AsyncSession],
    lock_statement: Select,
    operations: Sequence[Callable[[], Coroutine[Any, Any, Response]]],
) -> tuple[list[Response], int]:
    tasks: list[asyncio.Task[Response]] = []
    async with sessions() as blocker:
        try:
            await blocker.execute(lock_statement)
            tasks = [asyncio.create_task(operation()) for operation in operations]
            blocked_connections = await wait_for_two_blocked_connections(engine)
            await blocker.commit()
            async with asyncio.timeout(15):
                return list(await asyncio.gather(*tasks)), blocked_connections
        finally:
            # Release our lock even on assertion failure; never leave HTTP tasks alive.
            await blocker.rollback()
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)


def write_evidence(
    directory: str,
    responses: list[Response],
    spans: Sequence[ReadableSpan],
    blocked_connections: int,
    postgres_version: str,
) -> None:
    """Allowlist-only export from synthetic tests, not a dump of request/DB contents."""
    allowed_attributes = {
        "request.id",
        "http.route",
        "http.request.method",
        "http.response.status_code",
        "auth.result",
        "rbac.decision",
        "rbac.allowed_roles",
        "db.operation.name",
        "db.collection.name",
        "db.lock.mode",
        "db.response.returned_rows",
        "stockflow.sale.item_count",
        "transaction.outcome",
        "error.type",
    }
    request_ids = {"demo-purchase-a", "demo-purchase-b"}
    selected = [
        s for s in spans if (s.attributes or {}).get("request.id") in request_ids
    ]
    origin = min(s.start_time for s in selected if s.start_time is not None)
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "commit": os.environ.get("GITHUB_SHA", "local"),
        "run_url": (
            f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/actions/runs/"
            f"{os.environ['GITHUB_RUN_ID']}"
            if "GITHUB_RUN_ID" in os.environ
            else None
        ),
        "scenario": "Duas compras disputando a última unidade",
        "data_kind": "synthetic",
        "transport": "HTTPX ASGITransport → FastAPI → SQLAlchemy async → PostgreSQL",
        "postgres_version": postgres_version,
        "isolation": "read committed",
        "blocked_connections": blocked_connections,
        "initial_stock": 1,
        "final_stock": 0,
        "persisted_sales": 1,
        "persisted_items": 1,
        "sale_stock_movements": 1,
        "responses": [
            {"request_id": r.headers["x-request-id"], "status_code": r.status_code}
            for r in responses
        ],
        "spans": [
            {
                "name": s.name,
                "trace_id": f"{s.context.trace_id:032x}",
                "span_id": f"{s.context.span_id:016x}",
                "parent_span_id": f"{s.parent.span_id:016x}" if s.parent else None,
                "start_ms": round((s.start_time - origin) / 1_000_000, 3),
                "duration_ms": round((s.end_time - s.start_time) / 1_000_000, 3),
                "status": s.status.status_code.name,
                "attributes": {
                    k: v
                    for k, v in (s.attributes or {}).items()
                    if k in allowed_attributes
                },
            }
            for s in sorted(selected, key=lambda span: span.start_time)
        ],
    }
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    (target / "last-item-race.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
