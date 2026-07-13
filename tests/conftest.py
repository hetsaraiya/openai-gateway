import base64
import json
import time
from dataclasses import dataclass
from typing import Optional

import fakeredis.aioredis
import pytest
import pytest_asyncio

from app.config import Settings
from app.credentials import CodexAccount
from app.quota import QuotaStore


def make_settings(strategy="fallback", **kw) -> Settings:
    return Settings(
        master_api_key="test-master",
        auth_dir=kw.get("auth_dir", "auth"),
        strategy=strategy,
        rate_limit_cooldown=kw.get("rate_limit_cooldown", 60),
        max_account_attempts=kw.get("max_account_attempts", 3),
        token_refresh_skew=kw.get("token_refresh_skew", 300),
        oauth_token_url=kw.get("oauth_token_url", "https://auth.test/oauth/token"),
        codex_base_url=kw.get("codex_base_url", "https://codex.test/backend"),
        opencode_go_base_url=kw.get("opencode_go_base_url", "https://go.test/v1"),
        opencode_go_api_keys=kw.get("opencode_go_api_keys", ""),
        codex_client_version=kw.get("codex_client_version", "0.139.0"),
        models_cache_ttl=kw.get("models_cache_ttl", 3600),
    )


def make_jwt(claims: dict) -> str:
    def seg(obj):
        return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()
    return f"{seg({'alg': 'none'})}.{seg(claims)}.sig"


def make_account(tmp_path, acct_id: str, account_id: Optional[str] = None,
                 exp_offset: int = 3600, settings: Optional[Settings] = None) -> CodexAccount:
    settings = settings or make_settings()
    data = {
        "OPENAI_API_KEY": None,
        "tokens": {
            "access_token": make_jwt({"exp": int(time.time()) + exp_offset}),
            "refresh_token": f"refresh-{acct_id}",
            "id_token": make_jwt({"https://api.openai.com/auth": {
                "chatgpt_account_id": account_id or acct_id, "chatgpt_plan_type": "plus"}}),
            "account_id": account_id or acct_id,
        },
        "last_refresh": "2026-04-24T12:00:00.000Z",
    }
    path = tmp_path / f"{acct_id}.json"
    path.write_text(json.dumps(data))
    return CodexAccount(path, data, settings)


@dataclass
class FakeAccount:
    """Lightweight stand-in for router tests (only needs id + daily_limit)."""
    id: str
    daily_limit: Optional[int] = None


@pytest_asyncio.fixture
async def quota():
    store = QuotaStore.__new__(QuotaStore)
    store._redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield store
    await store._redis.aclose()


@pytest.fixture
def three_accounts():
    return [FakeAccount("a", 10), FakeAccount("b", 10), FakeAccount("c", None)]


def sse_bytes(events: list[dict]) -> bytes:
    return b"".join(b"data: " + json.dumps(e).encode() + b"\n\n" for e in events)


def completed_stream(text="Hello", model="gpt-5.1-codex") -> bytes:
    return sse_bytes([
        {"type": "response.output_text.delta", "delta": text},
        {"type": "response.completed", "response": {
            "id": "resp_test", "model": model, "status": "completed",
            "output": [{"type": "message", "role": "assistant",
                        "content": [{"type": "output_text", "text": text}]}],
            "usage": {"input_tokens": 5, "output_tokens": 1, "total_tokens": 6},
        }},
    ])
