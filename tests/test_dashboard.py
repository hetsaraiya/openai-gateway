import httpx
import pytest

from app.credentials import OpenCodeGoAccount
from app.main import _dashboard_html, app
from app.router import AccountRouter
from tests.conftest import make_account, make_settings


class Catalog:
    async def openai_list(self):
        return {
            "object": "list",
            "data": [
                {"id": "gpt-5-codex", "object": "model"},
                {"id": "opencode-go/glm-5.2", "object": "model", "gateway": "opencode-go"},
                {"id": "opencode-go/minimax-m3", "object": "model", "gateway": "opencode-go"},
            ],
        }


def test_dashboard_html_uses_an_origin_relative_data_path():
    html = _dashboard_html()

    assert 'const dashboardDataPath = "/dashboard/data";' in html
    assert "fetch(dashboardDataPath" in html
    assert "localhost" not in html


@pytest.mark.asyncio
async def test_dashboard_data_has_json_safe_provider_and_endpoint_rows(tmp_path, quota, monkeypatch):
    settings = make_settings()
    codex = make_account(tmp_path, "codex", settings=settings)
    go = OpenCodeGoAccount(None, {"api_key": "go_test_123456"}, settings, "go")
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    app.state.settings = settings
    app.state.router = AccountRouter(settings, [codex, go], quota)
    app.state.quota = quota
    app.state.catalog = Catalog()

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.get("/dashboard/data")
        assert denied.status_code == 401

        response = await client.get("/dashboard/data", headers={"X-Gateway-Key": "test-master"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"]["strategy"] == "fallback"
    assert payload["gateways"] == [
        {"id": "codex", "provider": "codex", "plan": "plus", "active": True, "used_today": 0},
        {"id": "go", "provider": "opencode-go", "plan": "opencode-go", "active": True, "used_today": 0},
    ]
    assert payload["models"][0]["supported_endpoints"] == ["/v1/responses", "/v1/chat/completions"]
    assert payload["models"][1]["supported_endpoints"] == [
        "/v1/chat/completions", "/v1/responses",
    ]
    assert payload["models"][2]["supported_endpoints"] == ["/v1/messages", "/v1/responses"]
    assert payload["providers"] == [
        {"id": "codex", "accounts": 1, "active_accounts": 1,
         "supported_endpoints": ["/v1/chat/completions", "/v1/responses"]},
        {"id": "opencode-go", "accounts": 1, "active_accounts": 1,
         "supported_endpoints": ["/v1/chat/completions", "/v1/messages", "/v1/responses"]},
    ]


@pytest.mark.asyncio
async def test_landing_page_is_public_and_serves_the_same_shell_as_the_dashboard():
    """The bundle picks landing vs console from the path, so both must load unauthenticated."""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        landing = await client.get("/")
        dashboard = await client.get("/dashboard")

    assert landing.status_code == 200
    assert dashboard.status_code == 200
    assert landing.text == dashboard.text


@pytest.mark.asyncio
async def test_dashboard_token_check_only_accepts_a_valid_master_key(monkeypatch):
    settings = make_settings()
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.post("/dashboard/auth/check")
        accepted = await client.post("/dashboard/auth/check", headers={"X-Gateway-Key": "test-master"})

    assert denied.status_code == 401
    assert accepted.status_code == 204
    assert accepted.content == b""


@pytest.mark.asyncio
async def test_delete_account_removes_router_entry_and_auth_file(tmp_path, quota, monkeypatch):
    settings = make_settings(auth_dir=str(tmp_path))
    account = make_account(tmp_path, "remove-me", settings=settings)
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    app.state.settings = settings
    app.state.router = AccountRouter(settings, [account], quota)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.delete("/admin/accounts/remove-me")
        deleted = await client.delete(
            "/admin/accounts/remove-me",
            headers={"X-Gateway-Key": "test-master"},
        )
        missing = await client.delete(
            "/admin/accounts/remove-me",
            headers={"X-Gateway-Key": "test-master"},
        )

    assert denied.status_code == 401
    assert deleted.status_code == 200
    assert deleted.json() == {"status": "ok", "account": "remove-me", "deleted": True}
    assert app.state.router.accounts() == []
    assert not (tmp_path / "remove-me.json").exists()
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_account_test_calls_selected_codex_account_models_endpoint(tmp_path, quota, monkeypatch):
    settings = make_settings()
    account = make_account(tmp_path, "primary", account_id="chatgpt-primary", settings=settings)
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    app.state.settings = settings
    app.state.router = AccountRouter(settings, [account], quota)

    async def upstream(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/backend/models"
        assert request.url.params["client_version"] == settings.codex_client_version
        assert request.headers["authorization"] == f"Bearer {account.access_token}"
        assert request.headers["chatgpt-account-id"] == "chatgpt-primary"
        return httpx.Response(200, json={"models": []})

    app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/admin/accounts/primary/test",
                headers={"X-Gateway-Key": "test-master"},
            )
    finally:
        await app.state.client.aclose()

    assert response.status_code == 200
    assert response.json()["account"] == "primary"
    assert response.json()["provider"] == "codex"
    assert response.json()["latency_ms"] >= 1


@pytest.mark.asyncio
async def test_account_test_calls_selected_opencode_go_models_endpoint(quota, monkeypatch):
    settings = make_settings()
    account = OpenCodeGoAccount(None, {"api_key": "go_test_123456"}, settings, "go-primary")
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    app.state.settings = settings
    app.state.router = AccountRouter(settings, [account], quota)

    async def upstream(request: httpx.Request) -> httpx.Response:
        assert request.url == f"{settings.opencode_go_base_url}/models"
        assert request.headers["authorization"] == "Bearer go_test_123456"
        return httpx.Response(200, json={"data": []})

    app.state.client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/admin/accounts/go-primary/test",
                headers={"X-Gateway-Key": "test-master"},
            )
    finally:
        await app.state.client.aclose()

    assert response.status_code == 200
    assert response.json()["account"] == "go-primary"
    assert response.json()["provider"] == "opencode-go"


@pytest.mark.asyncio
async def test_account_test_reports_upstream_rejection(tmp_path, quota, monkeypatch):
    settings = make_settings()
    account = make_account(tmp_path, "broken", settings=settings)
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    app.state.settings = settings
    app.state.router = AccountRouter(settings, [account], quota)
    app.state.client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(401))
    )

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/admin/accounts/broken/test",
                headers={"X-Gateway-Key": "test-master"},
            )
    finally:
        await app.state.client.aclose()

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "account_test_failed"
    assert "HTTP 401" in response.json()["error"]["message"]


@pytest.mark.asyncio
async def test_messages_rejects_opencode_models_without_messages_support(quota, monkeypatch):
    settings = make_settings()
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    app.state.settings = settings
    app.state.router = AccountRouter(settings, [], quota)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/messages",
            headers={"X-Gateway-Key": "test-master"},
            json={"model": "opencode-go/glm-5.2", "max_tokens": 10, "messages": []},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported_endpoint"
