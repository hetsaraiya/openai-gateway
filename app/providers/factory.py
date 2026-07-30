from __future__ import annotations

from dataclasses import dataclass

import httpx

from ..config import Settings
from ..router import AccountRouter
from .codex import CodexProvider
from .opencode_go import OpenCodeGoProvider
from .xai import XAIProvider


@dataclass(frozen=True)
class ProviderRegistry:
    codex: CodexProvider
    opencode_go: OpenCodeGoProvider
    xai: XAIProvider


class ProviderFactory:
    @staticmethod
    def create(
        settings: Settings,
        router: AccountRouter,
        client: httpx.AsyncClient,
    ) -> ProviderRegistry:
        return ProviderRegistry(
            codex=CodexProvider(settings, router, client),
            opencode_go=OpenCodeGoProvider(settings, router, client),
            xai=XAIProvider(settings, router, client),
        )
