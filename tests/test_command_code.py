import json

import httpx
import pytest

from app.credentials import CommandCodeAccount, load_accounts
from app.model_catalog import ModelCatalog
from app.proxy import CommandCodeProxy
from app.router import AccountRouter
from tests.conftest import make_settings


def make_command_code(tmp_path, settings=None, account_id="command-code-primary"):
    settings = settings or make_settings(auth_dir=str(tmp_path))
    path = tmp_path / f"{account_id}.json"
    data = {"type": "command-code", "api_key": "cmd_test_key_123456"}
    path.write_text(json.dumps(data))
    return CommandCodeAccount(path, data, settings)


def test_loads_command_code_file_and_environment_keys(tmp_path):
    settings = make_settings(
        auth_dir=str(tmp_path),
        command_code_api_keys="cmd_env_key_123456,cmd_env_key_654321",
    )
    make_command_code(tmp_path, settings)

    accounts = load_accounts(settings)

    assert [(account.id, account.provider, account.plan) for account in accounts] == [
        ("command-code-primary", "command-code", "command-code-api"),
        ("command-code-env-1", "command-code", "command-code-api"),
        ("command-code-env-2", "command-code", "command-code-api"),
    ]


@pytest.mark.asyncio
async def test_command_code_chat_uses_provider_endpoint(tmp_path, quota):
    settings = make_settings(auth_dir=str(tmp_path))
    account = make_command_code(tmp_path, settings)
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
        proxy = CommandCodeProxy(settings, router, client)
        selected, response = await proxy.open_chat({
            "model": "command-code/deepseek/deepseek-v4-flash",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        })
        payload = response.json()
        await response.aclose()

    assert selected.id == "command-code-primary"
    assert seen == {
        "url": "https://command-code.test/provider/v1/chat/completions",
        "authorization": "Bearer cmd_test_key_123456",
        "json": {
            "model": "deepseek/deepseek-v4-flash",
            "messages": [{"role": "user", "content": "hi"}],
            "stream": False,
        },
    }
    assert payload["choices"][0]["message"]["content"] == "hello"


@pytest.mark.asyncio
async def test_command_code_catalog_prefixes_live_models(tmp_path, quota):
    settings = make_settings(auth_dir=str(tmp_path))
    account = make_command_code(tmp_path, settings)
    router = AccountRouter(settings, [account], quota)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/provider/v1/models"
        assert request.headers["authorization"] == "Bearer cmd_test_key_123456"
        return httpx.Response(200, json={"data": [{
            "id": "deepseek/deepseek-v4-flash",
            "owned_by": "deepseek",
            "display_name": "DeepSeek V4 Flash",
        }]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        catalog = ModelCatalog(settings, router, client)
        result = await catalog.openai_list()

    assert result["data"] == [{
        "id": "command-code/deepseek/deepseek-v4-flash",
        "owned_by": "deepseek",
        "display_name": "DeepSeek V4 Flash",
        "object": "model",
        "gateway": "command-code",
        "supported_in_api": True,
        "supported_endpoints": ["/v1/chat/completions"],
    }]
