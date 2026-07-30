"""Backward-compatible exports for provider implementations."""

from .constants import (
    CODEX_SUPPORTED_ENDPOINTS,
    OPENCODE_GO_CHAT_ENDPOINT,
    OPENCODE_GO_MESSAGES_ENDPOINT,
    OPENCODE_GO_MESSAGES_MODELS,
    OPENCODE_GO_MODEL_PREFIX,
    XAI_SUPPORTED_ENDPOINTS,
)
from .providers.base import AllAccountsFailed
from .providers.codex import CodexProvider, build_codex_headers
from .providers.opencode_go import (
    OpenCodeGoProvider,
    build_opencode_go_headers,
    build_opencode_go_messages_headers,
    is_opencode_go_model,
    strip_opencode_go_model,
)
from .providers.xai import (
    XAIProvider,
    build_xai_headers,
    is_xai_model,
    strip_xai_model,
)

CodexProxy = CodexProvider
OpenCodeGoProxy = OpenCodeGoProvider
XAIProxy = XAIProvider

__all__ = [
    "AllAccountsFailed",
    "CODEX_SUPPORTED_ENDPOINTS",
    "CodexProxy",
    "OPENCODE_GO_CHAT_ENDPOINT",
    "OPENCODE_GO_MESSAGES_ENDPOINT",
    "OPENCODE_GO_MESSAGES_MODELS",
    "OPENCODE_GO_MODEL_PREFIX",
    "OpenCodeGoProxy",
    "XAIProxy",
    "XAI_SUPPORTED_ENDPOINTS",
    "build_codex_headers",
    "build_opencode_go_headers",
    "build_opencode_go_messages_headers",
    "build_xai_headers",
    "is_opencode_go_model",
    "is_xai_model",
    "strip_opencode_go_model",
    "strip_xai_model",
]
