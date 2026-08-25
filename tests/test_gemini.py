import json

import httpx
import pytest

from app.credentials import GeminiAccount, load_accounts
from app.model_catalog import ModelCatalog
from app.proxy import GeminiProxy
from app.router import AccountRouter
from tests.conftest import make_settings


def make_gemini(tmp_path, settings=None, account_id="gemini-primary"):
    settings = settings or make_settings(auth_dir=str(tmp_path))
    path = tmp_path / f"{account_id}.json"
    data = {"type": "gemini", "api_key": "gemini_test_key_123456"}
    path.write_text(json.dumps(data))
    return GeminiAccount(path, data, settings)


def test_loads_gemini_file_and_environment_keys(tmp_path):
    settings = make_settings(
        auth_dir=str(tmp_path),
        gemini_api_keys="env_gemini_key_123456,env_gemini_key_654321",
    )
    make_gemini(tmp_path, settings)

    accounts = load_accounts(settings)

    assert [(account.id, account.provider, account.plan) for account in accounts] == [
        ("gemini-primary", "gemini", "gemini-api"),
        ("gemini-env-1", "gemini", "gemini-api"),
        ("gemini-env-2", "gemini", "gemini-api"),
    ]


@pytest.mark.asyncio
async def test_gemini_chat_uses_openai_compatibility_endpoint(tmp_path, quota):
    settings = make_settings(auth_dir=str(tmp_path))
    account = make_gemini(tmp_path, settings)
    router = AccountRouter(settings, [account], quota)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["authorization"] = request.headers["authorization"]
        seen["json"] = json.loads(request.content)
        return httpx.Response(200, json={
            "choices": [{"message": {"role": "assistant", "content": "hello"}}]
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        proxy = GeminiProxy(settings, router, client)
        selected, response = await proxy.open_chat({
            "model": "gemini/gemini-3.7-flash",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        })
        payload = response.json()
        await response.aclose()

    assert selected.id == "gemini-primary"
    assert seen == {
        "url": "https://gemini.test/v1beta/openai/chat/completions",
        "authorization": "Bearer gemini_test_key_123456",
        "json": {
            "model": "gemini-3.7-flash",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        },
    }
    assert payload["choices"][0]["message"]["content"] == "hello"


@pytest.mark.asyncio
async def test_gemini_catalog_lists_only_chat_models(tmp_path, quota):
    settings = make_settings(auth_dir=str(tmp_path))
    account = make_gemini(tmp_path, settings)
    router = AccountRouter(settings, [account], quota)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1beta/openai/models"
        assert request.headers["authorization"] == "Bearer gemini_test_key_123456"
        return httpx.Response(200, json={"data": [
            {"id": "gemini-3.7-flash", "owned_by": "google"},
            {"id": "gemini-embedding-001", "owned_by": "google"},
            {"id": "imagen-4.0", "owned_by": "google"},
        ]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        catalog = ModelCatalog(settings, router, client)
        result = await catalog.openai_list()

    assert result["data"] == [{
        "id": "gemini/gemini-3.7-flash",
        "owned_by": "google",
        "object": "model",
        "display_name": "gemini-3.7-flash",
        "gateway": "gemini",
        "supported_in_api": True,
        "supported_endpoints": ["/v1/chat/completions"],
    }]
