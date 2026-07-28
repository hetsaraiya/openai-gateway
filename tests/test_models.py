import httpx
import pytest

from app.model_catalog import ModelCatalog, ModelCatalogError
from app.router import AccountRouter
from tests.conftest import make_account, make_settings

pytestmark = pytest.mark.asyncio

CATALOG = {"models": [
    {"slug": "gpt-5.5-codex", "display_name": "GPT-5.5 Codex", "description": "d",
     "visibility": "list", "supported_in_api": True, "context_window": 272000, "priority": 1,
     "input_modalities": ["text", "image"]},
    {"slug": "gpt-5.5", "display_name": "GPT-5.5", "visibility": "list",
     "supported_in_api": True, "context_window": 400000, "priority": 0},
    {"slug": "internal-secret", "display_name": "hidden", "visibility": "hidden", "priority": 5},
]}


def _catalog(tmp_path, handler, client_version="0.145.0", models_cache_ttl=3600):
    settings = make_settings(codex_client_version=client_version, models_cache_ttl=models_cache_ttl)
    accounts = [make_account(tmp_path, "a", settings=settings)]
    from app.quota import QuotaStore
    import fakeredis.aioredis
    q = QuotaStore.__new__(QuotaStore)
    q._redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    router = AccountRouter(settings, accounts, q)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return ModelCatalog(settings, router, client), client


async def test_openai_list_maps_and_filters(tmp_path):
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        seen["path"] = req.url.path
        seen["cv"] = req.url.params.get("client_version")
        seen["auth"] = req.headers.get("authorization")
        return httpx.Response(200, json=CATALOG, headers={"etag": "v1"})

    cat, client = _catalog(tmp_path, handler)
    try:
        out = await cat.openai_list()
        ids = [m["id"] for m in out["data"]]
        assert out["object"] == "list"
        assert ids == ["gpt-5.5-codex", "gpt-5.5"]      # hidden one filtered out
        assert "internal-secret" not in ids
        first = out["data"][0]
        assert first["object"] == "model" and first["owned_by"] == "openai"
        assert first["context_window"] == 272000
        assert seen["path"].endswith("/models")
        assert seen["cv"] == "0.145.0"
        assert seen["auth"].startswith("Bearer ")
    finally:
        await client.aclose()


async def test_default_model_is_highest_priority(tmp_path):
    def handler(req): return httpx.Response(200, json=CATALOG)
    cat, client = _catalog(tmp_path, handler)
    try:
        # priority 0 (gpt-5.5) sorts ahead of priority 1.
        assert await cat.default_model() == "gpt-5.5"
    finally:
        await client.aclose()


async def test_catalog_is_cached(tmp_path):
    calls = {"n": 0}

    def handler(req):
        calls["n"] += 1
        return httpx.Response(200, json=CATALOG, headers={"etag": "v1"})

    cat, client = _catalog(tmp_path, handler)
    try:
        await cat.openai_list()
        await cat.openai_list()
        assert calls["n"] == 1   # second call served from cache (within TTL)
    finally:
        await client.aclose()


async def test_revalidation_uses_etag_and_serves_cache_on_304(tmp_path):
    state = {"n": 0}

    def handler(req):
        state["n"] += 1
        if state["n"] == 1:
            return httpx.Response(200, json=CATALOG, headers={"etag": "v1"})
        assert req.headers.get("if-none-match") == "v1"
        return httpx.Response(304, headers={"etag": "v1"})

    cat, client = _catalog(tmp_path, handler, models_cache_ttl=0)  # force revalidation
    try:
        await cat.openai_list()
        out = await cat.openai_list()           # TTL=0 -> revalidate -> 304 -> stale cache
        assert state["n"] == 2
        assert [m["id"] for m in out["data"]] == ["gpt-5.5-codex", "gpt-5.5"]
    finally:
        await client.aclose()


async def test_error_when_no_cache_and_fetch_fails(tmp_path):
    def handler(req): return httpx.Response(500, json={"error": "boom"})
    cat, client = _catalog(tmp_path, handler)
    try:
        with pytest.raises(ModelCatalogError):
            await cat.openai_list()
    finally:
        await client.aclose()
