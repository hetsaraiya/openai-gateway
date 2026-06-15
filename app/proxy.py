"""Forwarding to the ChatGPT Codex backend (Responses API) with failover.

Given a Responses-format body, :meth:`CodexProxy.open_stream` selects a healthy
account, ensures its OAuth access token is fresh, opens a streaming POST to
``{codex_base_url}/responses`` with Codex's headers, and returns the live
``httpx.Response`` for the caller to consume. On a ``429``/``5xx``/transport
error it advances to the next account; on a ``401`` it force-refreshes the
token once before moving on.
"""

from __future__ import annotations

import logging
import uuid
from typing import Optional

import httpx

from .config import Settings
from .credentials import CodexAccount, CredentialError
from .router import AccountRouter, NoAccountAvailable

log = logging.getLogger("gateway.proxy")

_RETRYABLE_STATUS = {429, 500, 502, 503, 504}


def build_codex_headers(settings: Settings, acct: CodexAccount, stream: bool) -> dict:
    """The headers Codex sends to the ChatGPT backend for an account."""
    headers = {
        "Authorization": f"Bearer {acct.access_token}",
        "OpenAI-Beta": settings.openai_beta,
        "originator": settings.originator,
        "session_id": str(uuid.uuid4()),
        "Content-Type": "application/json",
        "Accept": "text/event-stream" if stream else "application/json",
    }
    if acct.account_id:
        headers["chatgpt-account-id"] = acct.account_id
    return headers


class AllAccountsFailed(Exception):
    def __init__(self, detail: str, status_code: int = 502):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class CodexProxy:
    def __init__(self, settings: Settings, router: AccountRouter, client: httpx.AsyncClient):
        self._settings = settings
        self._router = router
        self._client = client

    def _headers(self, acct: CodexAccount, stream: bool) -> dict:
        return build_codex_headers(self._settings, acct, stream)

    @staticmethod
    def _retry_after(resp: httpx.Response) -> Optional[int]:
        val = resp.headers.get("retry-after")
        try:
            return int(float(val)) if val else None
        except ValueError:
            return None

    async def open_stream(self, responses_body: dict) -> tuple[CodexAccount, httpx.Response]:
        """Open a streaming Responses request on the best available account."""
        url = f"{self._settings.codex_base_url}/responses"
        candidates = await self._router.candidates()  # raises NoAccountAvailable

        last_error = "no attempts made"
        for acct in candidates:
            try:
                resp = await self._attempt(acct, url, responses_body)
            except CredentialError as exc:
                last_error = f"{acct.id}: {exc}"
                log.warning("token problem on %s: %s", acct.id, exc)
                continue
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.RemoteProtocolError) as exc:
                last_error = f"{acct.id}: transport error: {exc}"
                log.warning(last_error)
                continue

            if resp is None:
                last_error = f"{acct.id}: retryable upstream status"
                continue

            await self._router.record_success(acct)
            return acct, resp

        raise AllAccountsFailed(f"all upstream attempts failed ({last_error})")

    async def _attempt(
        self, acct: CodexAccount, url: str, body: dict
    ) -> Optional[httpx.Response]:
        """One account, with a single forced-refresh retry on 401.

        Returns the open response, or ``None`` if the status is retryable
        (account already benched as appropriate) so the caller moves on.
        """
        for forced in (False, True):
            await acct.ensure_fresh(self._client, force=forced)
            req = self._client.build_request(
                "POST", url, headers=self._headers(acct, stream=True), json=body,
                timeout=self._settings.request_timeout,
            )
            resp = await self._client.send(req, stream=True)

            if resp.status_code == 401 and not forced:
                await resp.aclose()
                log.info("401 on %s — forcing token refresh and retrying", acct.id)
                continue

            if resp.status_code in _RETRYABLE_STATUS:
                if resp.status_code == 429:
                    await self._router.record_rate_limited(acct, self._retry_after(resp))
                log.info("retrying past %s -> HTTP %s", acct.id, resp.status_code)
                await resp.aclose()
                return None

            return resp  # success (2xx) or a non-retryable client error we pass through
        return None
