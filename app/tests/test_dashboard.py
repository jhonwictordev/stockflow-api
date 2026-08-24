from decimal import Decimal

from httpx import AsyncClient

from app.tests.conftest import RegisterUser
from app.tests.test_inventory_sales import create_product


async def test_dashboard_summary_is_calculated_for_the_current_tenant(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    _, headers = await register_user(client)
    product = await create_product(client, headers, stock=10)
    await client.post(
        "/api/v1/sales",
        headers=headers,
        json={"items": [{"product_id": product["id"], "quantity": 2}]},
    )

    response = await client.get("/api/v1/dashboard/summary", headers=headers)

    assert response.status_code == 200
    summary = response.json()
    assert summary["active_products"] == 1
    assert summary["stock_units"] == 8
    assert summary["low_stock_products"] == 0
    assert Decimal(summary["inventory_value"]) == Decimal("1004.00")
    assert summary["completed_sales"] == 1
    assert Decimal(summary["sales_revenue"]) == Decimal("251.00")
    assert len(summary["recent_sales"]) == 1
