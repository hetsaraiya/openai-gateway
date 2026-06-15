import httpx
import pytest

from app.proxy import AllAccountsFailed, CodexProxy
from app.router import AccountRouter
from tests.conftest import completed_stream, make_account, make_settings

pytestmark = pytest.mark.asyncio


def _proxy(quota, accounts, transport, strategy="fallback"):
    settings = make_settings(strategy)
    router = AccountRouter(settings, accounts, quota)
    client = httpx.AsyncClient(transport=transport)
    return CodexProxy(settings, router, client), client


async def test_sends_codex_headers_and_succeeds(quota, tmp_path):
    accounts = [make_account(tmp_path, "a", account_id="cg-a")]
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["acct"] = request.headers.get("chatgpt-account-id")
        seen["beta"] = request.headers.get("openai-beta")
        seen["url"] = str(request.url)
        return httpx.Response(200, content=completed_stream(),
                              headers={"content-type": "text/event-stream"})

    proxy, client = _proxy(quota, accounts, httpx.MockTransport(handler))
    try:
        acct, resp = await proxy.open_stream({"model": "gpt-5.1-codex", "input": []})
        assert resp.status_code == 200
        assert acct.id == "a"
        assert seen["auth"].startswith("Bearer ")
        assert seen["acct"] == "cg-a"
        assert seen["beta"] == "responses=experimental"
        assert seen["url"].endswith("/backend/responses")
        assert await quota.used_today("a") == 1
        await resp.aclose()
    finally:
        await client.aclose()


async def test_fails_over_on_429(quota, tmp_path):
    accounts = [make_account(tmp_path, "a", account_id="cg-a"),
                make_account(tmp_path, "b", account_id="cg-b")]
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        acct = request.headers.get("chatgpt-account-id")
        calls.append(acct)
        if acct == "cg-a":
            return httpx.Response(429, headers={"retry-after": "30"}, json={"error": "rate"})
        return httpx.Response(200, content=completed_stream(),
                              headers={"content-type": "text/event-stream"})

    proxy, client = _proxy(quota, accounts, httpx.MockTransport(handler))
    try:
        acct, resp = await proxy.open_stream({"model": "m", "input": []})
        assert acct.id == "b"
        assert calls == ["cg-a", "cg-b"]
        assert await quota.is_cooling_down("a")
        await resp.aclose()
    finally:
        await client.aclose()


async def test_401_forces_one_refresh_then_moves_on(quota, tmp_path, monkeypatch):
    # Account whose token is "expired" so ensure_fresh would refresh; we stub the
    # refresh to a no-op and have upstream always 401 -> account is abandoned.
    acct = make_account(tmp_path, "a", account_id="cg-a", exp_offset=-10)
    refreshed = {"n": 0}

    async def fake_refresh(self, client):
        refreshed["n"] += 1
    monkeypatch.setattr("app.credentials.CodexAccount._refresh", fake_refresh)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    proxy, client = _proxy(quota, [acct], httpx.MockTransport(handler))
    try:
        a, resp = await proxy.open_stream({"model": "m", "input": []})
        # 401 is non-retryable -> returned to caller (after one forced refresh).
        assert resp.status_code == 401
        assert refreshed["n"] >= 1
        await resp.aclose()
    finally:
        await client.aclose()


async def test_all_accounts_fail_raises(quota, tmp_path):
    accounts = [make_account(tmp_path, "a"), make_account(tmp_path, "b")]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "down"})

    proxy, client = _proxy(quota, accounts, httpx.MockTransport(handler))
    try:
        with pytest.raises(AllAccountsFailed):
            await proxy.open_stream({"model": "m", "input": []})
    finally:
        await client.aclose()
