import asyncio
import math
import time
from collections import deque
from collections.abc import Iterable

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class RequestBodyTooLargeError(Exception):
    pass


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_body_bytes: int) -> None:
        self.app = app
        self.max_body_bytes = max_body_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        content_length = headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > self.max_body_bytes:
                    await self._reject(scope, receive, send)
                    return
            except ValueError:
                await self._reject(scope, receive, send)
                return

        received_bytes = 0
        response_started = False

        async def limited_receive() -> Message:
            nonlocal received_bytes
            message = await receive()
            if message["type"] == "http.request":
                received_bytes += len(message.get("body", b""))
                if received_bytes > self.max_body_bytes:
                    raise RequestBodyTooLargeError
            return message

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracked_send)
        except RequestBodyTooLargeError:
            if response_started:
                raise
            await self._reject(scope, receive, send)

    @staticmethod
    async def _reject(scope: Scope, receive: Receive, send: Send) -> None:
        response = JSONResponse(
            status_code=413,
            content={"detail": "Corpo da requisição excede o limite permitido"},
            headers={"Cache-Control": "no-store"},
        )
        await response(scope, receive, send)


class RateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        requests: int,
        window_seconds: int,
        paths: Iterable[str],
        max_clients: int,
    ) -> None:
        self.app = app
        self.requests = requests
        self.window_seconds = window_seconds
        self.paths = frozenset(paths)
        self.max_clients = max_clients
        self._requests_by_client: dict[tuple[str, str], deque[float]] = {}
        self._lock = asyncio.Lock()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"] not in self.paths
        ):
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        client_host = client[0] if client else "unknown"
        key = (client_host, scope["path"])
        now = time.monotonic()

        async with self._lock:
            timestamps = self._requests_by_client.get(key)
            if timestamps is None:
                if len(self._requests_by_client) >= self.max_clients:
                    self._requests_by_client.pop(next(iter(self._requests_by_client)))
                timestamps = deque()
                self._requests_by_client[key] = timestamps

            cutoff = now - self.window_seconds
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= self.requests:
                retry_after = max(
                    1, math.ceil(timestamps[0] + self.window_seconds - now)
                )
                response = JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Muitas tentativas. Tente novamente mais tarde."
                    },
                    headers={
                        "Cache-Control": "no-store",
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(self.requests),
                        "X-RateLimit-Remaining": "0",
                    },
                )
                await response(scope, receive, send)
                return

            timestamps.append(now)
            remaining = self.requests - len(timestamps)

        async def send_with_rate_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = MutableHeaders(scope=message)
                response_headers["X-RateLimit-Limit"] = str(self.requests)
                response_headers["X-RateLimit-Remaining"] = str(remaining)
            await send(message)

        await self.app(scope, receive, send_with_rate_headers)
