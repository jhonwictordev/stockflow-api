import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from opentelemetry.trace import SpanKind, Status, StatusCode
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

from app.api.landing import render_landing_page
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import DomainError
from app.core.middleware import RateLimitMiddleware, RequestBodyLimitMiddleware
from app.core.observability import (
    bind_request_id,
    configure_logging_context,
    configure_observability,
    extract_trace_context,
    mark_span_error,
    normalize_request_id,
    reset_request_id,
    shutdown_observability,
    traced_span,
)

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format=(
        "%(asctime)s %(levelname)s %(name)s "
        "request_id=%(request_id)s trace_id=%(trace_id)s %(message)s"
    ),
)
configure_logging_context()
configure_observability()
logger = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).resolve().parent / "static"

OPENAPI_TAGS = [
    {
        "name": "Autenticação",
        "description": "Cadastro de organizações, login OAuth2 e perfil autenticado.",
    },
    {
        "name": "Dashboard",
        "description": "Indicadores consolidados para a interface administrativa.",
    },
    {
        "name": "Usuários",
        "description": "Administração de usuários e funções dentro da organização.",
    },
    {
        "name": "Produtos",
        "description": "Catálogo, saldo e histórico de movimentações de estoque.",
    },
    {
        "name": "Vendas",
        "description": "Registro transacional, consulta e cancelamento de vendas.",
    },
    {
        "name": "Infraestrutura",
        "description": "Verificações operacionais da aplicação e do banco de dados.",
    },
]


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        yield
    finally:
        shutdown_observability()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "API RESTful multi-tenant para gestão de estoque e vendas, "
        "com autenticação JWT e autorização RBAC."
    ),
    docs_url="/docs" if settings.docs_enabled else None,
    redoc_url="/redoc" if settings.docs_enabled else None,
    openapi_url="/openapi.json" if settings.docs_enabled else None,
    openapi_tags=OPENAPI_TAGS,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.ALLOWED_HOSTS)
app.add_middleware(
    RateLimitMiddleware,
    requests=settings.AUTH_RATE_LIMIT_REQUESTS,
    window_seconds=settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
    paths=(
        f"{settings.API_V1_PREFIX}/auth/register",
        f"{settings.API_V1_PREFIX}/auth/token",
    ),
    max_clients=settings.RATE_LIMIT_MAX_CLIENTS,
)
app.add_middleware(
    RequestBodyLimitMiddleware,
    max_body_bytes=settings.MAX_REQUEST_BODY_BYTES,
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def add_request_id(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = normalize_request_id(request.headers.get("X-Request-ID"))
    request_id_token = bind_request_id(request_id)
    request.state.request_id = request_id
    trace_context = extract_trace_context(request.headers)
    method = request.method.upper()
    try:
        with traced_span(
            f"HTTP {method}",
            kind=SpanKind.SERVER,
            context=trace_context,
            attributes={"http.request.method": method},
        ) as request_span:
            try:
                response = await call_next(request)
            except Exception:
                mark_span_error(request_span, "unhandled_request_error")
                raise

            route = request.scope.get("route")
            route_pattern = getattr(route, "path", "unmatched")
            if (
                route_pattern != "unmatched"
                and request.url.path.startswith(settings.API_V1_PREFIX)
                and not route_pattern.startswith(settings.API_V1_PREFIX)
            ):
                route_pattern = f"{settings.API_V1_PREFIX}{route_pattern}"
            request_span.update_name(f"{method} {route_pattern}")
            request_span.set_attribute("http.route", route_pattern)
            request_span.set_attribute(
                "http.response.status_code",
                response.status_code,
            )
            if response.status_code >= 500:
                request_span.set_status(Status(StatusCode.ERROR))

            response.headers["X-Request-ID"] = request_id
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["Permissions-Policy"] = (
                "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
            )
            if request.url.path in {"/docs", "/redoc"}:
                response.headers["Content-Security-Policy"] = (
                    "default-src 'self'; "
                    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                    "img-src 'self' data: https://fastapi.tiangolo.com; "
                    "font-src 'self' data:; connect-src 'self'; object-src 'none'; "
                    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
                )
            else:
                response.headers["Content-Security-Policy"] = (
                    "default-src 'self'; script-src 'self'; "
                    "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                    "font-src 'self' data:; connect-src 'self'; object-src 'none'; "
                    "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
                )
            if settings.ENVIRONMENT == "production":
                response.headers["Strict-Transport-Security"] = (
                    "max-age=63072000; includeSubDomains; preload"
                )
            if request.url.path.startswith(f"{settings.API_V1_PREFIX}/auth/"):
                response.headers["Cache-Control"] = "no-store"
                response.headers["Pragma"] = "no-cache"
            return response
    finally:
        reset_request_id(request_id_token)


@app.exception_handler(DomainError)
async def handle_domain_error(_: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})


@app.exception_handler(Exception)
async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    logger.exception("Unhandled request error request_id=%s", request_id, exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erro interno do servidor", "request_id": request_id},
    )


@app.get("/", include_in_schema=False)
async def landing_page() -> Response:
    return Response(
        content=render_landing_page(),
        media_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/painel", include_in_schema=False)
async def admin_panel() -> FileResponse:
    return FileResponse(STATIC_DIR / "dashboard.html")


@app.get(
    "/health",
    tags=["Infraestrutura"],
    summary="Verificar a saúde da aplicação",
)
async def health_check(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    await db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "reachable"}


app.include_router(api_router, prefix=settings.API_V1_PREFIX)
