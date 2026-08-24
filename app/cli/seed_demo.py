import argparse
import asyncio
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.models.product import Product
from app.models.user import User
from app.schemas.auth import RegisterRequest
from app.schemas.product import ProductCreate
from app.services.auth import register_tenant
from app.services.products import create_product


@dataclass(frozen=True)
class DemoResult:
    user: User
    created_organization: bool
    created_products: int


DEMO_PRODUCTS = (
    ProductCreate(
        name="Notebook Pro 14",
        sku="NOTE-PRO-14",
        description="Notebook de alto desempenho para equipes profissionais",
        price=Decimal("7499.90"),
        stock_quantity=12,
        minimum_stock=3,
    ),
    ProductCreate(
        name="Monitor UltraWide 34",
        sku="MON-UW-34",
        description="Monitor WQHD para produtividade",
        price=Decimal("2899.00"),
        stock_quantity=8,
        minimum_stock=2,
    ),
    ProductCreate(
        name="Teclado Mecânico",
        sku="KEY-MECH-01",
        description="Teclado mecânico hot-swappable",
        price=Decimal("459.90"),
        stock_quantity=25,
        minimum_stock=5,
    ),
)


async def seed_demo(
    db: AsyncSession,
    *,
    email: str,
    password: str,
) -> DemoResult:
    user = await db.scalar(select(User).where(User.email == email.lower()))
    created_organization = user is None
    if user is None:
        user = await register_tenant(
            db,
            RegisterRequest(
                organization_name="StockFlow Demo",
                full_name="Usuário de Demonstração",
                email=email,
                password=password,
            ),
        )

    existing_skus = set(
        await db.scalars(select(Product.sku).where(Product.tenant_id == user.tenant_id))
    )
    created_products = 0
    for product_data in DEMO_PRODUCTS:
        if product_data.sku not in existing_skus:
            await create_product(db, user, product_data)
            created_products += 1

    return DemoResult(
        user=user,
        created_organization=created_organization,
        created_products=created_products,
    )


async def async_main(email: str, password: str) -> None:
    if settings.ENVIRONMENT.lower() == "production":
        raise RuntimeError("A carga de demonstração não pode rodar em produção")

    async with AsyncSessionLocal() as db:
        result = await seed_demo(db, email=email, password=password)

    action = "criada" if result.created_organization else "já existente"
    print(f"Organização de demonstração {action}.")
    print(f"Produtos adicionados: {result.created_products}")
    print(f"Login: {email}")
    print(f"Senha: {password}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cria dados locais de demonstração")
    parser.add_argument("--email", default="demo@stockflow.dev")
    parser.add_argument("--password", default="Demo@12345")
    args = parser.parse_args()
    asyncio.run(async_main(args.email, args.password))


if __name__ == "__main__":
    main()
