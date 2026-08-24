from httpx import AsyncClient

from app.tests.conftest import RegisterUser
from app.tests.test_inventory_sales import create_product


async def login_headers(client: AsyncClient, email: str) -> dict[str, str]:
    response = await client.post(
        "/api/v1/auth/token",
        data={"username": email, "password": "strong-password"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_role_permissions_are_enforced(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    _, owner_headers = await register_user(client)
    product = await create_product(client, owner_headers)

    salesperson = await client.post(
        "/api/v1/users",
        headers=owner_headers,
        json={
            "email": "sales@example.com",
            "full_name": "Sales Person",
            "password": "strong-password",
            "role": "salesperson",
        },
    )
    assert salesperson.status_code == 201
    sales_headers = await login_headers(client, "sales@example.com")

    forbidden_product = await client.post(
        "/api/v1/products",
        headers=sales_headers,
        json={
            "name": "Forbidden Product",
            "sku": "NOPE",
            "price": "1.00",
            "stock_quantity": 1,
        },
    )
    assert forbidden_product.status_code == 403

    allowed_sale = await client.post(
        "/api/v1/sales",
        headers=sales_headers,
        json={"items": [{"product_id": product["id"], "quantity": 1}]},
    )
    assert allowed_sale.status_code == 201
    forbidden_cancel = await client.post(
        f"/api/v1/sales/{allowed_sale.json()['id']}/cancel", headers=sales_headers
    )
    assert forbidden_cancel.status_code == 403


async def test_admin_cannot_assign_peer_or_modify_owner(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    registration, owner_headers = await register_user(client)
    admin = await client.post(
        "/api/v1/users",
        headers=owner_headers,
        json={
            "email": "admin@example.com",
            "full_name": "Admin User",
            "password": "strong-password",
            "role": "admin",
        },
    )
    assert admin.status_code == 201
    admin_headers = await login_headers(client, "admin@example.com")

    peer = await client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "email": "peer@example.com",
            "full_name": "Peer Admin",
            "password": "strong-password",
            "role": "admin",
        },
    )
    assert peer.status_code == 403

    owner_update = await client.patch(
        f"/api/v1/users/{registration['user']['id']}",
        headers=admin_headers,
        json={"full_name": "Changed Owner"},
    )
    assert owner_update.status_code == 403


async def test_tenant_data_is_isolated(
    client: AsyncClient, register_user: RegisterUser
) -> None:
    _, tenant_a_headers = await register_user(client, "owner-a@example.com", "Tenant A")
    product = await create_product(client, tenant_a_headers, sku="PRIVATE")

    _, tenant_b_headers = await register_user(client, "owner-b@example.com", "Tenant B")
    detail = await client.get(
        f"/api/v1/products/{product['id']}", headers=tenant_b_headers
    )
    assert detail.status_code == 404

    listing = await client.get("/api/v1/products", headers=tenant_b_headers)
    assert listing.status_code == 200
    assert listing.json()["total"] == 0
