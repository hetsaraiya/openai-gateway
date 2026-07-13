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
from .proxy import OPENCODE_GO_MODEL_PREFIX, build_codex_headers, build_opencode_go_headers
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
        data.extend(await self._opencode_go_models())
        if not data and codex_error:
            raise codex_error
        return {"object": "list", "data": data}

    async def default_model(self) -> Optional[str]:
        """Highest-priority listable model slug, used when a request omits one."""
        await self._ensure()
        visible = self._visible()
        if not visible:
            return None
        # Lower `priority` sorts first (it's an ordering weight); fall back to
        # input order for ties / missing values.
        visible.sort(key=lambda m: m.get("priority", 1_000_000))
        return visible[0].get("slug")

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
        }
