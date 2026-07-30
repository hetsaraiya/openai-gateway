from __future__ import annotations

from typing import Any

from ..constants import (
    CHAT_API_SAFE_VARIABLES,
    MESSAGES_API_SAFE_VARIABLES,
    OPENCODE_GO_MODEL_PREFIX,
)
from .base import CompletionProvider, ProviderAccount


def is_opencode_go_model(model: str | None) -> bool:
    return bool(model and model.startswith(OPENCODE_GO_MODEL_PREFIX))


def strip_opencode_go_model(model: str) -> str:
    return model[len(OPENCODE_GO_MODEL_PREFIX) :]


def build_opencode_go_headers(account, stream: bool) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {account.access_token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream" if stream else "application/json",
    }


def build_opencode_go_messages_headers(account) -> dict[str, str]:
    return {
        "x-api-key": account.access_token,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }


class OpenCodeGoProvider(CompletionProvider):
    provider = "opencode-go"
    display_name = "OpenCode Go"
    api_safe_variables = {
        "/chat/completions": CHAT_API_SAFE_VARIABLES,
        "/messages": MESSAGES_API_SAFE_VARIABLES,
    }

    def url(self, path: str) -> str:
        return f"{self.settings.opencode_go_base_url}{path}"

    def prepare_body(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        prepared = super().prepare_body(path, body)
        model = prepared.get("model")
        if is_opencode_go_model(model):
            prepared["model"] = strip_opencode_go_model(model)
        return prepared

    def build_headers(
        self,
        account: ProviderAccount,
        body: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, str]:
        if context.get("anthropic"):
            return build_opencode_go_messages_headers(account)
        return build_opencode_go_headers(account, bool(body.get("stream")))

    async def open_chat(self, body: dict[str, Any]):
        return await self.open_completion("/chat/completions", body)

    async def open_messages(self, body: dict[str, Any]):
        return await self.open_completion(
            "/messages", body, context={"anthropic": True}
        )
