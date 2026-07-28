import json
import time

import httpx
import pytest

from app.credentials import CredentialError, XAIAccount, load_accounts
from app.model_catalog import ModelCatalog
from app.proxy import XAIProxy
from app.router import AccountRouter
from app.xai_login import XAILoginManager
from tests.conftest import make_jwt, make_settings


def xai_data(**overrides):
    data = {
        "type": "xai-oauth",
        "access_token": make_jwt({"exp": int(time.time()) + 3600}),
        "refresh_token": "refresh-xai",
        "id_token": make_jwt({"sub": "user-123", "email": "user@example.com"}),
        "expires_at": int(time.time()) + 3600,
        "user_id": "user-123",
        "email": "user@example.com",
        "client_id": "xai-client",
        "token_endpoint": "https://auth.xai.test/oauth2/token",
    }
    data.update(overrides)
    return data


def make_xai(tmp_path, settings=None, account_id="grok-primary", **overrides):
    settings = settings or make_settings(auth_dir=str(tmp_path))
    path = tmp_path / f"{account_id}.json"
    data = xai_data(**overrides)
    path.write_text(json.dumps(data))
    return XAIAccount(path, data, settings)


def test_loads_only_xai_oauth_accounts(tmp_path):
    settings = make_settings(auth_dir=str(tmp_path))
    (tmp_path / "grok.json").write_text(json.dumps(xai_data()))
    (tmp_path / "old-xai-key.json").write_text(
        json.dumps({"type": "xai", "api_key": "xai_old_key_123456"})
    )

    accounts = load_accounts(settings)

    assert [(account.id, account.provider, account.plan) for account in accounts] == [
        ("grok", "xai", "grok-subscription")
    ]
    with pytest.raises(CredentialError, match="require Grok subscription OAuth"):
        XAIAccount(None, {"type": "xai", "api_key": "xai_old_key_123456"}, settings)


@pytest.mark.asyncio
async def test_xai_oauth_refresh_rotates_and_persists_tokens(tmp_path):
    settings = make_settings(auth_dir=str(tmp_path), token_refresh_skew=300)
    account = make_xai(
        tmp_path,
        settings,
        access_token=make_jwt({"exp": int(time.time()) - 1}),
        expires_at=int(time.time()) - 1,
    )

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://auth.xai.test/oauth2/token"
        assert request.headers["x-grok-client-version"] == "0.2.112"
        assert request.content.decode() == (
            "grant_type=refresh_token&refresh_token=refresh-xai&client_id=xai-client"
        )
        return httpx.Response(200, json={
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 7200,
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await account.ensure_fresh(client)

    saved = json.loads(account.path.read_text())
    assert account.access_token == "new-access"
    assert saved["refresh_token"] == "new-refresh"
    assert saved["expires_at"] > int(time.time()) + 7000


@pytest.mark.asyncio
async def test_xai_device_login_uses_official_flow_and_saves_subscription(tmp_path, quota):
    settings = make_settings(auth_dir=str(tmp_path))
    router = AccountRouter(settings, [], quota)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        assert request.headers["x-grok-client-version"] == "0.2.112"
        if request.url.path.endswith("/device/code"):
            return httpx.Response(200, json={
                "device_code": "device-secret",
                "user_code": "ABCD-EFGH",
                "verification_uri": "https://accounts.x.ai/oauth2/device",
                "verification_uri_complete": "https://accounts.x.ai/oauth2/device?code=ABCD-EFGH",
                "expires_in": 900,
                "interval": 1,
            })
        return httpx.Response(200, json={
            "access_token": make_jwt({"exp": int(time.time()) + 3600}),
            "refresh_token": "refresh-new",
            "id_token": make_jwt({"sub": "xai-user", "email": "xai@example.com"}),
            "expires_in": 3600,
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        manager = XAILoginManager(settings, router, client)
        login = await manager.start("grok-team")
        await login.task

    assert login.status == "complete"
    assert login.provider == "xai"
    assert len(calls) == 2
    assert json.loads((tmp_path / "grok-team.json").read_text())["type"] == "xai-oauth"
    assert router.accounts()[0].account_id == "xai-user"


@pytest.mark.asyncio
async def test_xai_chat_uses_subscription_headers_and_cache_affinity(tmp_path, quota):
    settings = make_settings(auth_dir=str(tmp_path))
    account = make_xai(tmp_path, settings)
    router = AccountRouter(settings, [account], quota)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = request.headers
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={
            "id": "chatcmpl_xai",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}}],
            "usage": {"prompt_tokens_details": {"cached_tokens": 128}},
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        proxy = XAIProxy(settings, router, client)
        _, response = await proxy.open_chat({
            "model": "xai/grok-4.5",
            "messages": [{"role": "user", "content": "hi"}],
            "prompt_cache_key": "conversation-123",
        }, conversation_id="conversation-123")

    assert seen["json"] == {
        "model": "grok-4.5",
        "messages": [{"role": "user", "content": "hi"}],
    }
    assert seen["headers"]["x-xai-token-auth"] == "xai-grok-cli"
    assert seen["headers"]["x-grok-client-identifier"] == "grok-shell"
    assert seen["headers"]["x-authenticateresponse"] == "authenticate-response"
    assert seen["headers"]["user-agent"].startswith("grok-pager/0.2.112")
    assert seen["headers"]["x-grok-model-override"] == "grok-4.5"
    assert seen["headers"]["x-grok-conv-id"] == "conversation-123"
    assert seen["headers"]["x-userid"] == "user-123"
    assert response.json()["usage"]["prompt_tokens_details"]["cached_tokens"] == 128


@pytest.mark.asyncio
async def test_xai_responses_maps_prompt_cache_key_to_header(tmp_path, quota):
    settings = make_settings(auth_dir=str(tmp_path))
    account = make_xai(tmp_path, settings)
    router = AccountRouter(settings, [account], quota)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["json"] = json.loads(request.content)
        seen["conversation"] = request.headers.get("x-grok-conv-id")
        return httpx.Response(200, json={"id": "resp_xai", "output": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        proxy = XAIProxy(settings, router, client)
        _, response = await proxy.open_responses({
            "model": "xai/grok-4.5",
            "input": "hi",
            "prompt_cache_key": "conversation-456",
        }, conversation_id="conversation-456")
        await response.aclose()

    assert seen == {
        "json": {"model": "grok-4.5", "input": "hi"},
        "conversation": "conversation-456",
    }


@pytest.mark.asyncio
async def test_model_catalog_uses_live_grok_subscription_models(tmp_path, quota):
    settings = make_settings(auth_dir=str(tmp_path))
    xai = make_xai(tmp_path, settings)
    router = AccountRouter(settings, [xai], quota)
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert request.url.path == "/v1/models"
        assert request.headers["x-xai-token-auth"] == "xai-grok-cli"
        return httpx.Response(200, json={"data": [{
            "id": "grok-4.5",
            "owned_by": "xai",
            "context_window": 256000,
            "input_modalities": ["text", "image"],
        }]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        catalog = ModelCatalog(settings, router, client)
        first = await catalog.openai_list()
        second = await catalog.openai_list()

    model = first["data"][0]
    assert model["id"] == "xai/grok-4.5"
    assert model["context_window"] == 256000
    assert model["prompt_caching"] is True
    assert second == first
    assert calls == 1
