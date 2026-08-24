from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.core.middleware import RateLimitMiddleware, RequestBodyLimitMiddleware


async def test_auth_rate_limit_returns_retry_after() -> None:
    limited_app = FastAPI()
    limited_app.add_middleware(
        RateLimitMiddleware,
        requests=2,
        window_seconds=60,
        paths=("/login",),
        max_clients=100,
    )

    @limited_app.post("/login")
    async def login() -> dict[str, bool]:
        return {"ok": True}

    async with AsyncClient(
        transport=ASGITransport(app=limited_app),
        base_url="http://test",
    ) as client:
        assert (await client.post("/login")).status_code == 200
        assert (await client.post("/login")).status_code == 200
        rejected = await client.post("/login")

    assert rejected.status_code == 429
    assert rejected.headers["retry-after"] == "60"
    assert rejected.headers["x-ratelimit-remaining"] == "0"


async def test_request_body_limit_rejects_large_payloads() -> None:
    limited_app = FastAPI()
    limited_app.add_middleware(RequestBodyLimitMiddleware, max_body_bytes=32)

    @limited_app.post("/payload")
    async def payload(request: Request) -> dict[str, int]:
        return {"size": len(await request.body())}

    async with AsyncClient(
        transport=ASGITransport(app=limited_app),
        base_url="http://test",
    ) as client:
        rejected = await client.post("/payload", content=b"x" * 33)

    assert rejected.status_code == 413
    assert rejected.headers["cache-control"] == "no-store"
