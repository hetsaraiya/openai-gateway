import json

import pytest

from app.credentials import CursorAccount, load_accounts
from app.cursor_cli import cursor_models, cursor_prompt_from_chat, cursor_prompt_from_responses
from tests.conftest import make_settings


def make_cursor_account(tmp_path):
    settings = make_settings(auth_dir=str(tmp_path))
    home = tmp_path / ".cursor-accounts" / "team-session"
    home.mkdir(parents=True)
    data = {
        "type": "cursor-cli",
        "home": "team-session",
        "email": "team@example.com",
    }
    path = tmp_path / "cursor-team.json"
    path.write_text(json.dumps(data))
    return settings, CursorAccount(path, data, settings)


def test_loads_cursor_subscription_marker(tmp_path):
    settings, _ = make_cursor_account(tmp_path)

    accounts = load_accounts(settings)

    assert [(account.id, account.provider, account.plan) for account in accounts] == [
        ("cursor-team", "cursor", "cursor-subscription")
    ]
    assert accounts[0].account_id == "team@example.com"


@pytest.mark.asyncio
async def test_cursor_models_are_live_from_cli(tmp_path, monkeypatch):
    settings, account = make_cursor_account(tmp_path)

    class Process:
        returncode = 0

        async def communicate(self):
            return (
                b"Available models\n\n"
                b"gpt-5.6-sol - GPT-5.6 Sol High Fast (default)\n"
                b"composer-2.5 - Composer 2.5\n\n"
                b"Tip: use --model <id>\n",
                b"",
            )

    async def create(*args, **kwargs):
        assert f"HOME={account.home}" in args
        assert args[-1] == "models"
        return Process()

    monkeypatch.setattr("app.cursor_cli.asyncio.create_subprocess_exec", create)

    models = await cursor_models(settings, account)

    assert [model["id"] for model in models] == [
        "cursor/gpt-5.6-sol",
        "cursor/composer-2.5",
    ]
    assert all(model["prompt_caching"] for model in models)


def test_cursor_prompt_adapters_preserve_roles_and_structured_input():
    prompt = cursor_prompt_from_chat([
        {"role": "system", "content": "Be concise."},
        {"role": "user", "content": [{"type": "text", "text": "Hello"}]},
    ])

    assert prompt == (
        'SYSTEM: Be concise.\n\n'
        'USER: [{"type": "text", "text": "Hello"}]'
    )
    assert cursor_prompt_from_responses({"question": "Hello"}) == '{"question": "Hello"}'
