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
