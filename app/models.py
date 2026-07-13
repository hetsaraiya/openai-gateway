"""Pydantic models for the request bodies and admin/health endpoints."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class ChatCompletionRequest(BaseModel):
    """OpenAI Chat Completions request.

    Only the common fields are declared (so the docs show an editable body);
    ``extra="allow"`` lets every other OpenAI field — ``temperature``, ``tools``,
    ``response_format``, etc. — pass straight through to the backend.
    """

    model_config = ConfigDict(extra="allow")

    model: Optional[str] = Field(
        default=None, description="Model id. Omit to use DEFAULT_MODEL or the catalog default.")
    messages: list[dict] = Field(default_factory=list, description="Chat messages.")
    stream: bool = Field(default=False, description="Stream the response as SSE.")


class ResponsesRequest(BaseModel):
    """OpenAI Responses request (passthrough to the Codex backend)."""

    model_config = ConfigDict(extra="allow")

    model: Optional[str] = Field(default=None, description="Model id.")
    input: Any = Field(default=None, description="Responses API input (string or items).")
    stream: bool = Field(default=False, description="Stream the response as SSE.")


class AccountStatus(BaseModel):
    id: str
    provider: str = "codex"
    account_id: Optional[str] = None
    plan: Optional[str] = None
    access_token: str  # masked
    expires_at: Optional[int] = None
    used_today: int
    cooling_down: bool


class HealthResponse(BaseModel):
    status: str
    version: str
    redis: str
    accounts: int
    strategy: str


class StatusResponse(BaseModel):
    strategy: str
    accounts: list[AccountStatus]
