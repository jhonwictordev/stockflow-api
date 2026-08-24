from pydantic import BaseModel, EmailStr, Field

from app.core.passwords import StrongPassword
from app.schemas.common import RequestModel
from app.schemas.user import UserRead


class RegisterRequest(RequestModel):
    organization_name: str = Field(min_length=2, max_length=120)
    full_name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: StrongPassword


class RegistrationResponse(BaseModel):
    user: UserRead
    access_token: str
    token_type: str = "bearer"


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
