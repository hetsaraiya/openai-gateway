import json
from types import SimpleNamespace

import httpx
import pytest

from app.credentials import CredentialError, OpenCodeGoAccount, load_accounts, save_account_file
from app.main import app
from app.model_catalog import ModelCatalog
from app.proxy import OpenCodeGoProxy
from app.router import AccountRouter
from tests.conftest import make_account, make_settings


def test_loads_opencode_go_account_file(tmp_path):
    settings = make_settings(auth_dir=str(tmp_path))
    path = tmp_path / "go.json"
    path.write_text(json.dumps({"type": "opencode-go", "api_key": "go_test_123456"}))

    accounts = load_accounts(settings)

    assert len(accounts) == 1
    assert accounts[0].provider == "opencode-go"
    assert accounts[0].plan == "opencode-go"
    assert accounts[0].masked_token() != "go_test_123456"


def test_rejects_unsafe_opencode_go_api_key(tmp_path):
    settings = make_settings(auth_dir=str(tmp_path))

    with pytest.raises(CredentialError):
        save_account_file(settings, "bad", {"type": "opencode-go", "api_key": "bad key"})


@pytest.mark.asyncio
async def test_admin_api_adds_and_persists_opencode_go_key(tmp_path, quota, monkeypatch):
    """The dedicated key endpoint is master-key protected and hot-loads keys."""
    settings = make_settings(auth_dir=str(tmp_path))
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    app.state.settings = settings
    app.state.router = AccountRouter(settings, [], quota)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        denied = await client.post(
            "/v1/admin/opencode-go/keys",
            json={"api_key": "go_test_123456"},
        )
        assert denied.status_code == 401

        created = await client.post(
            "/v1/admin/opencode-go/keys",
            headers={"X-Gateway-Key": "test-master"},
            json={
                "api_key": "go_test_123456",
                "identifier": "go-primary",
                "label": "Primary Go subscription",
            },
        )
        assert created.status_code == 201
        assert created.json() == {
            "status": "ok",
            "id": "go-primary",
            "label": "Primary Go subscription",
            "replaced": False,
            "provider": "opencode-go",
        }

        replaced = await client.post(
            "/v1/admin/opencode-go/keys",
            headers={"Authorization": "Bearer test-master"},
            json={"api_key": "go_replacement_987654", "identifier": "go-primary"},
        )

    assert replaced.status_code == 200
    assert replaced.json()["replaced"] is True
    stored = json.loads((tmp_path / "go-primary.json").read_text())
    assert stored == {"type": "opencode-go", "api_key": "go_replacement_987654"}
    accounts = app.state.router.accounts()
    assert len(accounts) == 1
    assert accounts[0].id == "go-primary"
    assert accounts[0].access_token == "go_replacement_987654"


@pytest.mark.asyncio
async def test_opencode_go_proxy_strips_model_prefix_and_sends_bearer(quota):
    settings = make_settings()
    account = OpenCodeGoAccount(None, {"api_key": "go_test_123456"}, settings, "go")
    router = AccountRouter(settings, [account], quota)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={
            "id": "chatcmpl_go",
            "object": "chat.completion",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    proxy = OpenCodeGoProxy(settings, router, client)
    try:
        acct, resp = await proxy.open_chat({
            "model": "opencode-go/glm-5.2",
            "messages": [{"role": "user", "content": "hi"}],
        })
        assert acct.id == "go"
        assert resp.status_code == 200
        assert seen["url"] == "https://go.test/v1/chat/completions"
        assert seen["auth"] == "Bearer go_test_123456"
        assert seen["json"]["model"] == "glm-5.2"
        await resp.aclose()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_opencode_go_messages_uses_anthropic_headers(quota):
    settings = make_settings()
    account = OpenCodeGoAccount(None, {"api_key": "go_test_123456"}, settings, "go")
    router = AccountRouter(settings, [account], quota)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["api_key"] = request.headers.get("x-api-key")
        seen["version"] = request.headers.get("anthropic-version")
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "msg_go", "type": "message"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    proxy = OpenCodeGoProxy(settings, router, client)
    try:
        _, response = await proxy.open_messages({
            "model": "opencode-go/minimax-m3", "max_tokens": 10, "messages": [],
        })
        assert response.status_code == 200
        assert seen["url"] == "https://go.test/v1/messages"
        assert seen["api_key"] == "go_test_123456"
        assert seen["version"] == "2023-06-01"
        assert seen["json"]["model"] == "minimax-m3"
        await response.aclose()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_opencode_go_native_responses_uses_responses_endpoint(quota):
    settings = make_settings()
    account = OpenCodeGoAccount(None, {"api_key": "go_test_123456"}, settings, "go")
    router = AccountRouter(settings, [account], quota)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "resp_go", "object": "response"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    proxy = OpenCodeGoProxy(settings, router, client)
    try:
        _, response = await proxy.open_responses({
            "model": "opencode-go/gpt-5.6-luna", "input": "hi",
        })
        assert seen["url"] == "https://go.test/v1/responses"
        assert seen["json"]["model"] == "gpt-5.6-luna"
        await response.aclose()
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_responses_endpoint_translates_for_chat_only_go_model(monkeypatch):
    settings = make_settings()
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    seen = {}

    class Proxy:
        async def open_chat(self, body):
            seen["body"] = body
            return SimpleNamespace(id="go"), httpx.Response(200, json={
                "id": "chatcmpl_go",
                "choices": [{"message": {"role": "assistant", "content": "ok"},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1},
            })

    app.state.settings = settings
    app.state.opencode_go_proxy = Proxy()
    app.state.dedup = None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            headers={"X-Gateway-Key": "test-master"},
            json={"model": "opencode-go/glm-5.2", "input": "hello"},
        )

    assert response.status_code == 200
    assert seen["body"]["model"] == "glm-5.2"
    assert seen["body"]["messages"] == [{"role": "user", "content": "hello"}]
    assert response.json()["object"] == "response"
    assert response.json()["output"][0]["content"][0]["text"] == "ok"


@pytest.mark.asyncio
async def test_responses_endpoint_emulates_unavailable_json_schema(monkeypatch):
    settings = make_settings()
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    seen = {}

    class Proxy:
        async def open_chat(self, body):
            seen["body"] = body
            return SimpleNamespace(id="go"), httpx.Response(200, json={
                "id": "chatcmpl_go",
                "choices": [{"message": {
                    "role": "assistant", "content": None, "tool_calls": [{
                        "id": "call_1", "type": "function", "function": {
                            "name": "__gateway_structured_output",
                            "arguments": '{"name":"Ada"}',
                        },
                    }],
                }, "finish_reason": "tool_calls"}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1},
            })

    app.state.settings = settings
    app.state.opencode_go_proxy = Proxy()
    app.state.dedup = None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            headers={"X-Gateway-Key": "test-master"},
            json={
                "model": "opencode-go/glm-5.2",
                "input": "Extract the name",
                "text": {"format": {
                    "type": "json_schema",
                    "name": "profile",
                    "schema": {
                        "type": "object",
                        "properties": {"name": {"type": "string"}},
                        "required": ["name"],
                    },
                    "strict": True,
                }},
            },
        )

    assert response.status_code == 200
    assert "response_format" not in seen["body"]
    assert "tool_choice" not in seen["body"]
    assert "__gateway_structured_output" in seen["body"]["messages"][0]["content"]
    assert response.json()["output"][0]["content"][0]["text"] == '{"name":"Ada"}'


@pytest.mark.asyncio
async def test_messages_responses_structured_output_supports_thinking_mode(monkeypatch):
    settings = make_settings()
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    seen = {}

    class Proxy:
        async def open_messages(self, body):
            seen["body"] = body
            return SimpleNamespace(id="go"), httpx.Response(200, json={
                "id": "msg_go",
                "type": "message",
                "stop_reason": "tool_use",
                "content": [{
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "__gateway_structured_output",
                    "input": {"name": "Ada"},
                }],
                "usage": {"input_tokens": 2, "output_tokens": 1},
            })

    app.state.settings = settings
    app.state.opencode_go_proxy = Proxy()
    app.state.dedup = None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            headers={"X-Gateway-Key": "test-master"},
            json={
                "model": "opencode-go/qwen3.8-max",
                "input": "Extract the name",
                "reasoning": {"effort": "high"},
                "text": {"format": {
                    "type": "json_schema",
                    "name": "profile",
                    "schema": {"type": "object", "properties": {
                        "name": {"type": "string"},
                    }},
                }},
            },
        )

    assert response.status_code == 200
    assert "tool_choice" not in seen["body"]
    assert "__gateway_structured_output" in seen["body"]["system"]
    assert response.json()["output"][0]["content"][0]["text"] == '{"name":"Ada"}'


@pytest.mark.asyncio
async def test_native_go_responses_also_emulates_unavailable_json_schema(monkeypatch):
    settings = make_settings()
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)
    seen = {}

    class Proxy:
        async def open_responses(self, body):
            seen["body"] = body
            return SimpleNamespace(id="go"), httpx.Response(200, json={
                "id": "resp_go", "object": "response", "status": "completed",
                "model": "gpt-5.6-luna",
                "output": [{
                    "id": "fc_1", "type": "function_call",
                    "name": "__gateway_structured_output", "call_id": "call_1",
                    "arguments": '{"name":"Ada"}', "status": "completed",
                }],
                "usage": {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
            })

    app.state.settings = settings
    app.state.opencode_go_proxy = Proxy()
    app.state.dedup = None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            headers={"X-Gateway-Key": "test-master"},
            json={
                "model": "opencode-go/gpt-5.6-luna",
                "input": "Extract the name",
                "text": {"format": {
                    "type": "json_schema", "name": "profile",
                    "schema": {"type": "object", "properties": {
                        "name": {"type": "string"},
                    }},
                }},
            },
        )

    assert response.status_code == 200
    assert "format" not in seen["body"].get("text", {})
    assert "tool_choice" not in seen["body"]
    assert "__gateway_structured_output" in seen["body"]["instructions"]
    assert response.json()["output"][0]["content"][0]["text"] == '{"name":"Ada"}'


@pytest.mark.asyncio
async def test_responses_endpoint_translates_chat_stream_to_responses_events(monkeypatch):
    settings = make_settings()
    monkeypatch.setattr("app.auth.get_settings", lambda: settings)

    class Proxy:
        async def open_chat(self, body):
            chunks = [
                {"choices": [{"delta": {"role": "assistant", "content": "ok"},
                              "finish_reason": "stop"}]},
                {"choices": [], "usage": {"prompt_tokens": 2, "completion_tokens": 1}},
            ]
            content = b"".join(
                b"data: " + json.dumps(chunk).encode() + b"\n\n" for chunk in chunks
            ) + b"data: [DONE]\n\n"
            return SimpleNamespace(id="go"), httpx.Response(
                200, content=content, headers={"content-type": "text/event-stream"}
            )

    app.state.settings = settings
    app.state.opencode_go_proxy = Proxy()
    app.state.dedup = None
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/responses",
            headers={"X-Gateway-Key": "test-master"},
            json={"model": "opencode-go/glm-5.2", "input": "hello", "stream": True},
        )

    assert response.status_code == 200
    events = [
        json.loads(block.removeprefix("data: "))
        for block in response.text.strip().split("\n\n")
    ]
    assert events[0]["type"] == "response.created"
    assert events[-1]["type"] == "response.completed"
    assert events[-1]["response"]["output"][0]["content"][0]["text"] == "ok"


@pytest.mark.asyncio
async def test_model_catalog_includes_opencode_go_models(tmp_path, quota):
    settings = make_settings()
    codex = make_account(tmp_path, "codex", settings=settings)
    go = OpenCodeGoAccount(None, {"api_key": "go_test_123456"}, settings, "go")
    router = AccountRouter(settings, [codex, go], quota)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "codex.test":
            return httpx.Response(200, json={"models": [{
                "slug": "gpt-5.5",
                "display_name": "GPT-5.5",
                "visibility": "list",
                "priority": 0,
            }]})
        return httpx.Response(200, json={"data": [{
            "id": "glm-5.2",
            "owned_by": "opencode-go",
            "context_window": 262144,
        }]})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    catalog = ModelCatalog(settings, router, client)
    try:
        out = await catalog.openai_list()
        ids = [m["id"] for m in out["data"]]
        assert ids == ["gpt-5.5", "opencode-go/glm-5.2"]
        assert out["data"][1]["supported_endpoints"] == [
            "/v1/chat/completions", "/v1/responses",
        ]
    finally:
        await client.aclose()
