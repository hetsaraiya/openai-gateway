import json

import httpx
import pytest

from app.credentials import CredentialError, OpenCodeGoAccount, load_accounts, save_account_file
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
    finally:
        await client.aclose()
