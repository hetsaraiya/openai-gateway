import json
from dataclasses import replace

import httpx
import pytest

from app.credentials import XAIAccount, load_accounts
from app.main import app
from app.model_catalog import ModelCatalog
from app.proxy import XAIProxy
from app.router import AccountRouter
from tests.conftest import make_account, make_settings


def test_loads_xai_account_file_and_environment_key(tmp_path):
    settings = make_settings(
        auth_dir=str(tmp_path),
        xai_api_keys="xai_environment_123456",
    )
    (tmp_path / "xai-primary.json").write_text(
        json.dumps({"type": "xai", "api_key": "xai_file_123456"})
    )

    accounts = load_accounts(settings)

    assert [(account.id, account.provider) for account in accounts] == [
        ("xai-primary", "xai"),
        ("xai-env-1", "xai"),
    ]
    assert all(account.masked_token() not in ("xai_file_123456", "xai_environment_123456") for account in accounts)


@pytest.mark.asyncio
async def test_admin_api_adds_and_persists_xai_key(tmp_path, quota, monkeypatch):
    settings = make_settings(auth_dir=str(tmp_path))
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    app.state.settings = settings
    app.state.router = AccountRouter(settings, [], quota)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.post("/v1/admin/xai/keys", json={"api_key": "xai_test_123456"})
        created = await client.post(
            "/v1/admin/xai/keys",
            headers={"X-Gateway-Key": "test-master"},
            json={
                "api_key": "xai_test_123456",
                "identifier": "xai-primary",
                "label": "Primary xAI key",
            },
        )

    assert denied.status_code == 401
    assert created.status_code == 201
    assert created.json()["provider"] == "xai"
    assert app.state.router.accounts()[0].provider == "xai"
    assert json.loads((tmp_path / "xai-primary.json").read_text()) == {
        "type": "xai",
        "api_key": "xai_test_123456",
        "label": "Primary xAI key",
    }


@pytest.mark.asyncio
async def test_xai_chat_uses_cache_routing_header_and_strips_gateway_fields(quota):
    settings = make_settings()
    account = XAIAccount(None, {"type": "xai", "api_key": "xai_test_123456"}, settings, "xai")
    router = AccountRouter(settings, [account], quota)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers.get("authorization")
        seen["conversation_id"] = request.headers.get("x-grok-conv-id")
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={
            "id": "chatcmpl_xai",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens_details": {"cached_tokens": 128}},
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    proxy = XAIProxy(settings, router, client)
    try:
        _, response = await proxy.open_chat(
            {
                "model": "xai/grok-4.5",
                "messages": [{"role": "user", "content": "hi"}],
                "prompt_cache_key": "conversation-123",
            },
            conversation_id="conversation-123",
        )
        payload = response.json()
        await response.aclose()
    finally:
        await client.aclose()

    assert seen == {
        "url": "https://xai.test/v1/chat/completions",
        "authorization": "Bearer xai_test_123456",
        "conversation_id": "conversation-123",
        "json": {
            "model": "grok-4.5",
            "messages": [{"role": "user", "content": "hi"}],
        },
    }
    assert payload["usage"]["prompt_tokens_details"]["cached_tokens"] == 128


@pytest.mark.asyncio
async def test_xai_responses_preserves_prompt_cache_key(quota):
    settings = make_settings()
    account = XAIAccount(None, {"type": "xai", "api_key": "xai_test_123456"}, settings, "xai")
    router = AccountRouter(settings, [account], quota)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "resp_xai", "output": []})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    proxy = XAIProxy(settings, router, client)
    try:
        _, response = await proxy.open_responses({
            "model": "xai/grok-4.5",
            "input": "hi",
            "prompt_cache_key": "conversation-456",
        })
        await response.aclose()
    finally:
        await client.aclose()

    assert seen["json"] == {
        "model": "grok-4.5",
        "input": "hi",
        "prompt_cache_key": "conversation-456",
    }


@pytest.mark.asyncio
async def test_chat_endpoint_routes_xai_and_enables_cache_affinity(quota, monkeypatch):
    settings = replace(make_settings(), dedup_enabled=False)
    account = XAIAccount(None, {"type": "xai", "api_key": "xai_test_123456"}, settings, "xai")
    router = AccountRouter(settings, [account], quota)

    def upstream(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-grok-conv-id"] == "conversation-api-test"
        body = json.loads(request.content)
        assert body["model"] == "grok-4.5"
        assert "prompt_cache_key" not in body
        return httpx.Response(200, json={
            "id": "chatcmpl_xai",
            "object": "chat.completion",
            "model": "grok-4.5",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
            "usage": {
                "prompt_tokens": 128,
                "completion_tokens": 1,
                "total_tokens": 129,
                "prompt_tokens_details": {"cached_tokens": 128},
            },
        })

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    app.state.settings = settings
    app.state.router = router
    app.state.xai_proxy = XAIProxy(settings, router, upstream_client)
    app.state.dedup = object()

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/completions",
                headers={"X-Gateway-Key": "test-master"},
                json={
                    "model": "xai/grok-4.5",
                    "messages": [{"role": "user", "content": "hi"}],
                    "prompt_cache_key": "conversation-api-test",
                },
            )
    finally:
        await upstream_client.aclose()

    assert response.status_code == 200
    assert response.headers["x-gateway-account"] == "xai"
    assert response.json()["usage"]["prompt_tokens_details"]["cached_tokens"] == 128


@pytest.mark.asyncio
async def test_responses_endpoint_routes_xai_and_preserves_zdr_header(quota, monkeypatch):
    settings = replace(make_settings(), dedup_enabled=False)
    account = XAIAccount(None, {"type": "xai", "api_key": "xai_test_123456"}, settings, "xai")
    router = AccountRouter(settings, [account], quota)

    def upstream(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body == {
            "model": "grok-4.5",
            "input": "hi",
            "prompt_cache_key": "responses-cache-key",
        }
        return httpx.Response(
            200,
            headers={"x-zero-data-retention": "true"},
            json={"id": "resp_xai", "object": "response", "output": []},
        )

    upstream_client = httpx.AsyncClient(transport=httpx.MockTransport(upstream))
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    app.state.settings = settings
    app.state.router = router
    app.state.xai_proxy = XAIProxy(settings, router, upstream_client)
    app.state.dedup = object()

    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/responses",
                headers={"X-Gateway-Key": "test-master"},
                json={
                    "model": "xai/grok-4.5",
                    "input": "hi",
                    "prompt_cache_key": "responses-cache-key",
                },
            )
    finally:
        await upstream_client.aclose()

    assert response.status_code == 200
    assert response.headers["x-gateway-account"] == "xai"
    assert response.headers["x-upstream-zero-data-retention"] == "true"


@pytest.mark.asyncio
async def test_model_catalog_includes_cached_xai_language_models(tmp_path, quota):
    settings = make_settings()
    codex = make_account(tmp_path, "codex", settings=settings)
    xai = XAIAccount(None, {"type": "xai", "api_key": "xai_test_123456"}, settings, "xai")
    router = AccountRouter(settings, [codex, xai], quota)
    xai_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal xai_calls
        if request.url.host == "codex.test":
            return httpx.Response(200, json={"models": []})
        xai_calls += 1
        assert request.url.path == "/v1/language-models"
        return httpx.Response(200, json={"models": [{
            "id": "grok-4.5",
            "owned_by": "xai",
            "context_length": 256000,
            "input_modalities": ["text", "image"],
            "output_modalities": ["text"],
            "cached_prompt_text_token_price": 5000,
        }]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    catalog = ModelCatalog(settings, router, client)
    try:
        first = await catalog.openai_list()
        second = await catalog.openai_list()
    finally:
        await client.aclose()

    model = first["data"][0]
    assert model["id"] == "xai/grok-4.5"
    assert model["gateway"] == "xai"
    assert model["context_window"] == 256000
    assert model["prompt_caching"] is True
    assert model["supported_endpoints"] == ["/v1/chat/completions", "/v1/responses"]
    assert second == first
    assert xai_calls == 1
