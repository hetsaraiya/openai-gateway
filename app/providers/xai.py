from __future__ import annotations

from typing import Any

from ..constants import (
    CHAT_API_SAFE_VARIABLES,
    RESPONSES_API_SAFE_VARIABLES,
    XAI_MODEL_PREFIX,
)
from .base import CompletionProvider, ProviderAccount


def is_xai_model(model: str | None) -> bool:
    return bool(model and model.startswith(XAI_MODEL_PREFIX))


def strip_xai_model(model: str) -> str:
    return model[len(XAI_MODEL_PREFIX) :]


def build_xai_headers(
    settings,
    account,
    stream: bool,
    conversation_id: str | None = None,
    model: str | None = None,
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {account.access_token}",
        "X-XAI-Token-Auth": "xai-grok-cli",
        "User-Agent": (
            f"grok-pager/{settings.grok_client_version} "
            f"grok-shell/{settings.grok_client_version} (linux; gateway)"
        ),
        "x-grok-client-identifier": "grok-shell",
        "x-grok-client-version": settings.grok_client_version,
        "x-grok-client-mode": "headless",
        "x-authenticateresponse": "authenticate-response",
        "Content-Type": "application/json",
        "Accept": "text/event-stream" if stream else "application/json",
    }
    if account.account_id:
        headers["x-userid"] = account.account_id
    if email := getattr(account, "_data", {}).get("email"):
        headers["x-email"] = email
    if conversation_id:
        headers["x-grok-conv-id"] = conversation_id
    if model:
        headers["x-grok-model-override"] = model
    return headers


class XAIProvider(CompletionProvider):
    provider = "xai"
    display_name = "xAI"
    retry_unauthorized = True
    api_safe_variables = {
        "/chat/completions": CHAT_API_SAFE_VARIABLES,
        "/responses": RESPONSES_API_SAFE_VARIABLES,
    }

    def url(self, path: str) -> str:
        return f"{self.settings.xai_base_url}{path}"

    def prepare_body(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        prepared = super().prepare_body(path, body)
        prepared["model"] = strip_xai_model(str(prepared.get("model") or ""))
        prepared.pop("prompt_cache_key", None)
        return prepared

    def build_headers(
        self,
        account: ProviderAccount,
        body: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, str]:
        return build_xai_headers(
            self.settings,
            account,
            bool(body.get("stream")),
            context.get("conversation_id"),
            str(body.get("model") or ""),
        )

    async def open_chat(
        self, body: dict[str, Any], conversation_id: str | None = None
    ):
        return await self.open_completion(
            "/chat/completions",
            body,
            context={"conversation_id": conversation_id},
        )

    async def open_responses(
        self, body: dict[str, Any], conversation_id: str | None = None
    ):
        return await self.open_completion(
            "/responses",
            body,
            context={"conversation_id": conversation_id},
        )
