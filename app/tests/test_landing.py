from httpx import AsyncClient


async def test_landing_page_is_in_portuguese_and_links_to_api_docs(
    client: AsyncClient,
) -> None:
    response = await client.get("/")

    assert response.status_code == 200
    assert "StockFlow" in response.text
    assert "Acessar painel" in response.text
    assert 'href="/docs"' in response.text
    assert 'href="/painel"' in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-request-id"]
    assert "default-src 'self'" in response.headers["content-security-policy"]


async def test_admin_panel_serves_the_portuguese_dashboard(
    client: AsyncClient,
) -> None:
    response = await client.get("/painel")

    assert response.status_code == 200
    assert "Estoque e vendas em um só fluxo" in response.text
    assert 'src="/static/app.js"' in response.text
    assert 'href="/static/styles.css"' in response.text


async def test_health_check_reports_database_status(client: AsyncClient) -> None:
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "reachable"}
