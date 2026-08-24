import logging
import uuid
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response
from starlette.staticfiles import StaticFiles

from app.api.landing import render_landing_page
from app.api.v1.router import api_router
from app.core.config import settings
from app.core.database import get_db
from app.core.exceptions import DomainError

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
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

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description=(
        "API RESTful multi-tenant para gestão de estoque e vendas, "
        "com autenticação JWT e autorização RBAC."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=OPENAPI_TAGS,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def add_request_id(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))[:128]
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "img-src 'self' data: https://fastapi.tiangolo.com; "
        "font-src 'self' data:; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    return response


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
