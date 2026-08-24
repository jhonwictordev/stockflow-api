from decimal import Decimal

from httpx import AsyncClient

from app.tests.conftest import RegisterUser


async def create_product(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    sku: str = "SKU-001",
    stock: int = 10,
) -> dict:
    response = await client.post(
        "/api/v1/products",
        headers=headers,
        json={
            "name": "Mechanical Keyboard",
            "sku": sku,
            "description": "Hot-swappable keyboard",
            "price": "125.50",
            "stock_quantity": stock,
            "minimum_stock": 2,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_sale_decrements_stock_and_cancellation_restores_it(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    _, headers = await register_user(client)
    product = await create_product(client, headers)
    assert product["is_low_stock"] is False

    sale_response = await client.post(
        "/api/v1/sales",
        headers=headers,
        json={
            "customer_name": "Customer One",
            "items": [{"product_id": product["id"], "quantity": 3}],
        },
    )
    assert sale_response.status_code == 201, sale_response.text
    sale = sale_response.json()
    assert Decimal(sale["total"]) == Decimal("376.50")
    assert sale["status"] == "completed"

    current_product = await client.get(
        f"/api/v1/products/{product['id']}", headers=headers
    )
    assert current_product.json()["stock_quantity"] == 7

    movements = await client.get(
        f"/api/v1/products/{product['id']}/stock-movements", headers=headers
    )
    assert movements.status_code == 200
    assert movements.json()["total"] == 2
    assert {item["movement_type"] for item in movements.json()["items"]} == {
        "initial",
        "sale",
    }

    cancelled = await client.post(f"/api/v1/sales/{sale['id']}/cancel", headers=headers)
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    restored_product = await client.get(
        f"/api/v1/products/{product['id']}", headers=headers
    )
    assert restored_product.json()["stock_quantity"] == 10

    repeated_cancel = await client.post(
        f"/api/v1/sales/{sale['id']}/cancel", headers=headers
    )
    assert repeated_cancel.status_code == 409


async def test_insufficient_stock_rolls_back_the_entire_sale(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    _, headers = await register_user(client)
    first = await create_product(client, headers, sku="FIRST", stock=5)
    second = await create_product(client, headers, sku="SECOND", stock=1)

    response = await client.post(
        "/api/v1/sales",
        headers=headers,
        json={
            "items": [
                {"product_id": first["id"], "quantity": 2},
                {"product_id": second["id"], "quantity": 2},
            ]
        },
    )
    assert response.status_code == 422

    unchanged = await client.get(f"/api/v1/products/{first['id']}", headers=headers)
    assert unchanged.json()["stock_quantity"] == 5
    sales = await client.get("/api/v1/sales", headers=headers)
    assert sales.json()["total"] == 0


async def test_manual_stock_adjustment_is_audited(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    _, headers = await register_user(client)
    product = await create_product(client, headers, stock=3)

    adjustment = await client.post(
        f"/api/v1/products/{product['id']}/stock-adjustments",
        headers=headers,
        json={"quantity": -2, "reason": "Damaged items"},
    )
    assert adjustment.status_code == 200
    assert adjustment.json()["stock_quantity"] == 1

    invalid = await client.post(
        f"/api/v1/products/{product['id']}/stock-adjustments",
        headers=headers,
        json={"quantity": -2, "reason": "Invalid negative balance"},
    )
    assert invalid.status_code == 422

    movements = await client.get(
        f"/api/v1/products/{product['id']}/stock-movements", headers=headers
    )
    assert movements.json()["total"] == 2
    assert movements.json()["items"][0]["reason"] == "Damaged items"
