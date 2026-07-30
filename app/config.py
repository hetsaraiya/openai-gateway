"""Gateway configuration.

Accounts are no longer API keys — each account is a Codex ``auth.json`` file
(ChatGPT "Sign in with ChatGPT" credentials) placed in ``AUTH_DIR``. The gateway
loads every ``*.json`` there, refreshes the OAuth ``access_token`` as needed, and
forwards requests to the ChatGPT Codex backend (Responses API).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from decouple import config

# Public OAuth client id used by the Codex CLI (overridable if OpenAI rotates it).
DEFAULT_CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
DEFAULT_XAI_CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
DEFAULT_XAI_SCOPES = (
    "openid profile email offline_access grok-cli:access api:access "
    "conversations:read conversations:write workspaces:read workspaces:write"
)


@dataclass(frozen=True)
class Settings:
    master_api_key: str
    auth_dir: str = "auth"
    redis_url: str = "redis://localhost:6379/0"

    # Upstream ChatGPT Codex backend (Responses API lives at {base}/responses).
    codex_base_url: str = "https://chatgpt.com/backend-api/codex"
    # OpenCode Go subscription endpoint. Depending on the selected model, the
    # gateway uses OpenAI-compatible chat completions or Anthropic Messages.
    opencode_go_base_url: str = "https://opencode.ai/zen/go/v1"
    opencode_go_api_keys: str = ""
    # Grok subscription endpoint and OAuth client used by the official CLI.
    xai_base_url: str = "https://cli-chat-proxy.grok.com/v1"
    xai_oauth_issuer: str = "https://auth.x.ai"
    xai_oauth_client_id: str = DEFAULT_XAI_CLIENT_ID
    xai_oauth_scopes: str = DEFAULT_XAI_SCOPES
    grok_client_version: str = "0.2.112"
    # Where access tokens are refreshed.
    oauth_token_url: str = "https://auth.openai.com/oauth/token"
    oauth_client_id: str = DEFAULT_CODEX_CLIENT_ID
    codex_binary: str = "codex"
    cursor_binary: str = "cursor-agent"
    # Refresh the access token this many seconds before it actually expires.
    token_refresh_skew: int = 300

    # Headers Codex sends to the backend.
    originator: str = "codex_cli_rs"
    openai_beta: str = "responses=experimental"
    # Sent as ?client_version= when listing models (the backend gates models on
    # a minimum client version). Defaults to a recent Codex CLI release.
    codex_client_version: str = "0.145.0"
    # How long to trust the fetched model catalog before revalidating (seconds).
    models_cache_ttl: int = 3600

    strategy: str = "fallback"  # round_robin | quota_aware | fallback
    rate_limit_cooldown: int = 60
    request_timeout: float = 600.0
    max_account_attempts: int = 3
    # Optional provider defaults applied only to explicitly allowlisted request
    # variables. Per-request values always take precedence.
    provider_safe_defaults: dict[str, dict[str, Any]] = field(default_factory=dict)

    dedup_enabled: bool = True
    dedup_ttl: int = 600

    # Default model for /v1/chat/completions when the client omits one. Empty
    # means "resolve from the live catalog" (highest-priority listed model).
    default_model: str = ""
    # Sent as `instructions` (required by the backend) when a chat request has no
    # system/developer message and no explicit `instructions`.
    default_instructions: str = "You are a helpful assistant."


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    master = config("GATEWAY_API_KEY", default="")
    if not master:
        raise RuntimeError("GATEWAY_API_KEY must be set (the master key clients use).")

    provider_safe_defaults = config("PROVIDER_SAFE_DEFAULTS", default="{}")
    try:
        parsed_safe_defaults = json.loads(provider_safe_defaults)
    except json.JSONDecodeError as exc:
        raise RuntimeError("PROVIDER_SAFE_DEFAULTS must be valid JSON.") from exc
    if not isinstance(parsed_safe_defaults, dict):
        raise RuntimeError("PROVIDER_SAFE_DEFAULTS must be a JSON object.")

    return Settings(
        master_api_key=master,
        auth_dir=config("AUTH_DIR", default="auth"),
        redis_url=config("REDIS_URL", default="redis://localhost:6379/0"),
        codex_base_url=config(
            "CODEX_BASE_URL", default="https://chatgpt.com/backend-api/codex"
        ).rstrip("/"),
        opencode_go_base_url=config(
            "OPENCODE_GO_BASE_URL", default="https://opencode.ai/zen/go/v1"
        ).rstrip("/"),
        opencode_go_api_keys=config("OPENCODE_GO_API_KEYS", default=""),
        xai_base_url=config(
            "XAI_BASE_URL", default="https://cli-chat-proxy.grok.com/v1"
        ).rstrip("/"),
        xai_oauth_issuer=config("XAI_OAUTH_ISSUER", default="https://auth.x.ai").rstrip("/"),
        xai_oauth_client_id=config("XAI_OAUTH_CLIENT_ID", default=DEFAULT_XAI_CLIENT_ID),
        xai_oauth_scopes=config("XAI_OAUTH_SCOPES", default=DEFAULT_XAI_SCOPES),
        grok_client_version=config("GROK_CLIENT_VERSION", default="0.2.112"),
        oauth_token_url=config(
            "OAUTH_TOKEN_URL", default="https://auth.openai.com/oauth/token"
        ),
        oauth_client_id=config("CODEX_CLIENT_ID", default=DEFAULT_CODEX_CLIENT_ID),
        codex_binary=config("CODEX_BINARY", default="codex"),
        cursor_binary=config("CURSOR_BINARY", default="cursor-agent"),
        token_refresh_skew=config("TOKEN_REFRESH_SKEW", default=300, cast=int),
        originator=config("CODEX_ORIGINATOR", default="codex_cli_rs"),
        openai_beta=config("CODEX_OPENAI_BETA", default="responses=experimental"),
        codex_client_version=config("CODEX_CLIENT_VERSION", default="0.145.0"),
        models_cache_ttl=config("MODELS_CACHE_TTL", default=3600, cast=int),
        strategy=config("ROUTING_STRATEGY", default="fallback"),
        rate_limit_cooldown=config("RATE_LIMIT_COOLDOWN", default=60, cast=int),
        request_timeout=config("REQUEST_TIMEOUT", default=600.0, cast=float),
        max_account_attempts=config("MAX_ACCOUNT_ATTEMPTS", default=3, cast=int),
        provider_safe_defaults=parsed_safe_defaults,
        dedup_enabled=config("DEDUP_ENABLED", default=True, cast=bool),
        dedup_ttl=config("DEDUP_TTL", default=600, cast=int),
        default_model=config("DEFAULT_MODEL", default=""),
        default_instructions=config(
            "DEFAULT_INSTRUCTIONS", default="You are a helpful assistant."),
    )
