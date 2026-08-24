from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user
from app.core.database import get_db
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.auth import RegisterRequest, RegistrationResponse, Token
from app.schemas.user import UserMe
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["Autenticação"])


def _token_for(user: User) -> str:
    return create_access_token(
        str(user.id),
        tenant_id=str(user.tenant_id),
        role=user.role.value,
    )


@router.post(
    "/register",
    response_model=RegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Cadastrar uma organização e seu proprietário",
)
async def register(
    data: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> RegistrationResponse:
    user = await auth_service.register_tenant(db, data)
    return RegistrationResponse(user=user, access_token=_token_for(user))


@router.post("/token", response_model=Token, summary="Obter um token de acesso")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
) -> Token:
    user = await auth_service.authenticate_user(
        db, form_data.username, form_data.password
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="E-mail ou senha incorretos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return Token(access_token=_token_for(user))


@router.get("/me", response_model=UserMe, summary="Consultar o usuário autenticado")
async def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user
