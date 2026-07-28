"""Live model catalog fetched from the Codex backend.

Instead of hardcoding model ids, this mirrors what the Codex CLI does: it does a
``GET {codex_base_url}/models?client_version=<v>`` (authenticated with a real
account token) and returns the ``{"models": [...]}`` payload. Results are cached
for ``models_cache_ttl`` seconds and revalidated with an ``ETag`` afterwards, so
``/v1/models`` reflects exactly what OpenAI currently serves the account.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import httpx

from .config import Settings
from .credentials import CredentialError
from .cursor_cli import cursor_models
from .proxy import (
    CODEX_SUPPORTED_ENDPOINTS,
    OPENCODE_GO_CHAT_ENDPOINT,
    OPENCODE_GO_MESSAGES_ENDPOINT,
    OPENCODE_GO_MESSAGES_MODELS,
    OPENCODE_GO_MODEL_PREFIX,
    build_codex_headers,
    build_opencode_go_headers,
    build_xai_headers,
)
from .router import AccountRouter, NoAccountAvailable

log = logging.getLogger("gateway.models")

_RETRYABLE = {429, 500, 502, 503, 504}


class ModelCatalogError(Exception):
    pass


class ModelCatalog:
    def __init__(self, settings: Settings, router: AccountRouter, client: httpx.AsyncClient):
        self._settings = settings
        self._router = router
        self._client = client
        self._lock = asyncio.Lock()
        self._raw: list[dict] = []          # raw ModelInfo objects from the backend
        self._opencode_go_raw: list[dict] = []
        self._xai_raw: list[dict] = []
        self._xai_fetched_at: float = 0.0
        self._xai_lock = asyncio.Lock()
        self._cursor_raw: list[dict] = []
        self._cursor_fetched_at: float = 0.0
        self._cursor_lock = asyncio.Lock()
        self._etag: Optional[str] = None
        self._fetched_at: float = 0.0

    @property
    def _url(self) -> str:
        return f"{self._settings.codex_base_url}/models"

    def _fresh(self) -> bool:
        return bool(self._raw) and (time.time() - self._fetched_at) < self._settings.models_cache_ttl

    async def _ensure(self) -> None:
        if self._fresh():
            return
        async with self._lock:
            if self._fresh():
                return
            await self._fetch()

    async def _fetch(self) -> None:
        try:
            candidates = await self._router.candidates("codex")
        except NoAccountAvailable as exc:
            if self._raw:
                log.warning("model catalog: no account available, serving stale cache (%s)", exc)
                return
            raise ModelCatalogError(str(exc)) from exc

        params = {"client_version": self._settings.codex_client_version}
        last_error = "no attempts"
        for acct in candidates:
            try:
                await acct.ensure_fresh(self._client)
                headers = build_codex_headers(self._settings, acct, stream=False)
                if self._etag:
                    headers["If-None-Match"] = self._etag
                resp = await self._client.get(
                    self._url, params=params, headers=headers, timeout=30.0,
                )
            except (CredentialError, httpx.HTTPError) as exc:
                last_error = f"{acct.id}: {exc}"
                continue

            if resp.status_code == 304 and self._raw:
                self._fetched_at = time.time()
                return
            if resp.status_code == 200:
                self._raw = (resp.json() or {}).get("models", [])
                self._etag = resp.headers.get("etag")
                self._fetched_at = time.time()
                log.info("model catalog refreshed via %s: %d models", acct.id, len(self._raw))
                return
            if resp.status_code in _RETRYABLE:
                last_error = f"{acct.id}: HTTP {resp.status_code}"
                continue
            # Non-retryable (e.g. 401/403) — report it.
            last_error = f"{acct.id}: HTTP {resp.status_code} {resp.text[:200]}"

        if self._raw:
            log.warning("model catalog refresh failed (%s); serving stale cache", last_error)
            return
        raise ModelCatalogError(f"could not fetch models ({last_error})")

    @staticmethod
    def _to_openai(m: dict) -> dict:
        """Map a Codex ModelInfo to an OpenAI /v1/models entry (+ useful extras)."""
        return {
            "id": m.get("slug"),
            "object": "model",
            "created": 0,
            "owned_by": "openai",
            "display_name": m.get("display_name"),
            "description": m.get("description"),
            "context_window": m.get("context_window"),
            "max_context_window": m.get("max_context_window"),
            "supported_in_api": m.get("supported_in_api"),
            "input_modalities": m.get("input_modalities"),
            "gateway": "codex",
            "supported_endpoints": list(CODEX_SUPPORTED_ENDPOINTS),
        }

    def _visible(self) -> list[dict]:
        # The backend marks publicly listable models with visibility == "list".
        return [m for m in self._raw if m.get("visibility", "list") == "list" and m.get("slug")]

    async def openai_list(self) -> dict:
        codex_error: Optional[ModelCatalogError] = None
        data: list[dict] = []
        try:
            await self._ensure()
            data.extend(self._to_openai(m) for m in self._visible())
        except ModelCatalogError as exc:
            codex_error = exc
        opencode_models, xai_models, cursor_catalog = await asyncio.gather(
            self._opencode_go_models(),
            self._xai_models(),
            self._cursor_models(),
        )
        data.extend(opencode_models)
        data.extend(xai_models)
        data.extend(cursor_catalog)
        if not data and codex_error:
            raise codex_error
        return {"object": "list", "data": data}

    async def default_model(self) -> Optional[str]:
        """Highest-priority listable model slug, used when a request omits one."""
        try:
            await self._ensure()
            visible = self._visible()
        except ModelCatalogError:
            visible = []
        if visible:
            # Lower `priority` sorts first (it's an ordering weight); fall back
            # to input order for ties / missing values.
            visible.sort(key=lambda m: m.get("priority", 1_000_000))
            return visible[0].get("slug")
        provider_models = await asyncio.gather(
            self._opencode_go_models(), self._xai_models(), self._cursor_models()
        )
        return next((model["id"] for models in provider_models for model in models), None)

    async def _cursor_models(self) -> list[dict]:
        if self._cursor_raw and (
            time.time() - self._cursor_fetched_at
        ) < self._settings.models_cache_ttl:
            return list(self._cursor_raw)
        async with self._cursor_lock:
            try:
                candidates = await self._router.candidates("cursor")
            except NoAccountAvailable:
                return []
            last_error = ""
            for account in candidates:
                try:
                    models = await cursor_models(self._settings, account)
                except (OSError, RuntimeError) as exc:
                    last_error = f"{account.id}: {exc}"
                    continue
                self._cursor_raw = models
                self._cursor_fetched_at = time.time()
                return list(models)
            if self._cursor_raw:
                log.warning("Cursor model refresh failed (%s); serving stale cache", last_error)
                return list(self._cursor_raw)
            log.warning("Cursor models unavailable (%s)", last_error or "no attempts")
            return []

    async def _opencode_go_models(self) -> list[dict]:
        try:
            candidates = await self._router.candidates("opencode-go")
        except NoAccountAvailable:
            return []

        last_error = ""
        for acct in candidates:
            try:
                resp = await self._client.get(
                    f"{self._settings.opencode_go_base_url}/models",
                    headers=build_opencode_go_headers(acct, stream=False),
                    timeout=30.0,
                )
            except httpx.HTTPError as exc:
                last_error = f"{acct.id}: {exc}"
                continue

            if resp.status_code == 200:
                models = (resp.json() or {}).get("data") or (resp.json() or {}).get("models") or []
                self._opencode_go_raw = models
                return [self._opencode_to_openai(m) for m in models if m.get("id") or m.get("slug")]
            if resp.status_code in _RETRYABLE:
                last_error = f"{acct.id}: HTTP {resp.status_code}"
                continue
            last_error = f"{acct.id}: HTTP {resp.status_code} {resp.text[:200]}"

        if self._opencode_go_raw:
            log.warning("OpenCode Go model refresh failed (%s); serving stale cache", last_error)
            return [self._opencode_to_openai(m) for m in self._opencode_go_raw if m.get("id") or m.get("slug")]
        log.warning("OpenCode Go models unavailable (%s)", last_error or "no attempts")
        return []

    @staticmethod
    def _opencode_to_openai(m: dict) -> dict:
        model_id = m.get("id") or m.get("slug")
        endpoint = (
            OPENCODE_GO_MESSAGES_ENDPOINT
            if model_id in OPENCODE_GO_MESSAGES_MODELS
            else OPENCODE_GO_CHAT_ENDPOINT
        )
        return {
            "id": f"{OPENCODE_GO_MODEL_PREFIX}{model_id}",
            "object": "model",
            "created": m.get("created", 0),
            "owned_by": m.get("owned_by") or "opencode-go",
            "display_name": m.get("name") or m.get("display_name") or model_id,
            "description": m.get("description"),
            "context_window": m.get("context_window"),
            "supported_in_api": True,
            "gateway": "opencode-go",
            "supported_endpoints": [endpoint],
        }

    async def _xai_models(self) -> list[dict]:
        if self._xai_raw and (time.time() - self._xai_fetched_at) < self._settings.models_cache_ttl:
            return [self._xai_to_openai(model) for model in self._xai_raw]
        async with self._xai_lock:
            if self._xai_raw and (time.time() - self._xai_fetched_at) < self._settings.models_cache_ttl:
                return [self._xai_to_openai(model) for model in self._xai_raw]
            return await self._fetch_xai_models()

    async def _fetch_xai_models(self) -> list[dict]:
        try:
            candidates = await self._router.candidates("xai")
        except NoAccountAvailable:
            return []

        last_error = ""
        for acct in candidates:
            try:
                await acct.ensure_fresh(self._client)
                response = await self._client.get(
                    f"{self._settings.xai_base_url}/models",
                    headers=build_xai_headers(self._settings, acct, stream=False),
                    timeout=30.0,
                )
            except (CredentialError, httpx.HTTPError) as exc:
                last_error = f"{acct.id}: {exc}"
                continue

            if response.status_code == 200:
                payload = response.json() or {}
                models = payload.get("data") or payload.get("models") or []
                self._xai_raw = [
                    model for model in models
                    if isinstance(model, dict) and (model.get("id") or model.get("model"))
                ]
                self._xai_fetched_at = time.time()
                return [self._xai_to_openai(model) for model in self._xai_raw]
            if response.status_code in _RETRYABLE:
                last_error = f"{acct.id}: HTTP {response.status_code}"
                continue
            last_error = f"{acct.id}: HTTP {response.status_code} {response.text[:200]}"

        if self._xai_raw:
            log.warning("xAI model refresh failed (%s); serving stale cache", last_error)
            return [self._xai_to_openai(model) for model in self._xai_raw]
        log.warning("xAI models unavailable (%s)", last_error or "no attempts")
        return []

    @staticmethod
    def _xai_to_openai(model: dict) -> dict:
        model_id = str(model.get("id") or model.get("model"))
        return {
            "id": f"xai/{model_id}",
            "object": "model",
            "created": model.get("created", 0),
            "owned_by": model.get("owned_by") or "xai",
            "display_name": model.get("name") or model.get("display_name") or model_id,
            "description": model.get("description"),
            "context_window": model.get("context_window") or model.get("context_length"),
            "input_modalities": model.get("input_modalities"),
            "output_modalities": model.get("output_modalities"),
            "gateway": "xai",
            "supported_in_api": True,
            "supported_endpoints": ["/v1/chat/completions", "/v1/responses"],
            "prompt_caching": True,
            "cached_prompt_text_token_price": model.get("cached_prompt_text_token_price"),
        }
