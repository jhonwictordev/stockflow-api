import uuid
from datetime import datetime

from pydantic import EmailStr, Field, field_validator, model_validator

from app.models.user import UserRole
from app.schemas.common import ORMModel, RequestModel


class TenantRead(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    created_at: datetime


class UserCreate(RequestModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=8, max_length=72)
    role: UserRole = UserRole.VIEWER

    @field_validator("role")
    @classmethod
    def owner_cannot_be_created(cls, value: UserRole) -> UserRole:
        if value is UserRole.OWNER:
            raise ValueError(
                "A função owner só pode ser criada no cadastro da organização"
            )
        return value


class UserUpdate(RequestModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=120)
    role: UserRole | None = None
    is_active: bool | None = None

    @field_validator("role")
    @classmethod
    def owner_role_is_immutable(cls, value: UserRole | None) -> UserRole | None:
        if value is UserRole.OWNER:
            raise ValueError("A função owner não pode ser atribuída")
        return value

    @model_validator(mode="after")
    def reject_empty_or_null_update(self) -> "UserUpdate":
        if not self.model_fields_set:
            raise ValueError("Informe ao menos um campo para atualização")
        nonnullable = {"full_name", "role", "is_active"}
        if any(
            field in self.model_fields_set and getattr(self, field) is None
            for field in nonnullable
        ):
            raise ValueError("Campos de usuário não podem receber null")
        return self


class UserRead(ORMModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserMe(UserRead):
    tenant: TenantRead
