import httpx
import pytest

from app.providers import (
    CodexProvider,
    OpenCodeGoProvider,
    ProviderFactory,
    XAIProvider,
)
from app.router import AccountRouter
from tests.conftest import make_settings


@pytest.mark.asyncio
async def test_factory_builds_complete_provider_registry(quota):
    settings = make_settings()
    router = AccountRouter(settings, [], quota)
    client = httpx.AsyncClient()

    providers = ProviderFactory.create(settings, router, client)

    assert isinstance(providers.codex, CodexProvider)
    assert isinstance(providers.opencode_go, OpenCodeGoProvider)
    assert isinstance(providers.xai, XAIProvider)
    assert providers.codex.router is router
    assert providers.xai.client is client
    await client.aclose()


@pytest.mark.asyncio
async def test_api_safe_provider_defaults_are_allowlisted_and_request_wins(quota):
    settings = make_settings(
        provider_safe_defaults={
            "xai": {
                "temperature": 0.2,
                "max_tokens": 100,
                "authorization": "must-not-pass",
            }
        }
    )
    router = AccountRouter(settings, [], quota)
    client = httpx.AsyncClient()
    provider = XAIProvider(settings, router, client)

    prepared = provider.prepare_body(
        "/chat/completions",
        {"model": "xai/grok-4.5", "temperature": 0.8}
    )

    assert prepared == {
        "model": "grok-4.5",
        "temperature": 0.8,
        "max_tokens": 100,
    }
    await client.aclose()
