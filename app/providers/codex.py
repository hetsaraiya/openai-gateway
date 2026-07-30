from __future__ import annotations

import uuid
from typing import Any

from ..credentials import CodexAccount
from .base import CompletionProvider


def build_codex_headers(
    settings, account: CodexAccount, stream: bool
) -> dict[str, str]:
    headers = {
        "Authorization": f"Bearer {account.access_token}",
        "OpenAI-Beta": settings.openai_beta,
        "originator": settings.originator,
        "session_id": str(uuid.uuid4()),
        "Content-Type": "application/json",
        "Accept": "text/event-stream" if stream else "application/json",
    }
    if account.account_id:
        headers["chatgpt-account-id"] = account.account_id
    return headers


class CodexProvider(CompletionProvider):
    provider = "codex"
    display_name = "Codex"
    retry_unauthorized = True

    def url(self, path: str) -> str:
        return f"{self.settings.codex_base_url}{path}"

    def build_headers(
        self,
        account: CodexAccount,
        body: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, str]:
        return build_codex_headers(self.settings, account, stream=True)

    async def open_stream(
        self, responses_body: dict[str, Any]
    ) -> tuple[CodexAccount, object]:
        return await self.open_completion("/responses", responses_body)
