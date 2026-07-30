from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Protocol

import httpx

from ..config import Settings
from ..constants import RETRYABLE_UPSTREAM_STATUSES
from ..credentials import CredentialError
from ..router import AccountRouter

log = logging.getLogger("gateway.providers")

TRANSPORT_ERRORS = (
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
)
REQUEST_ERRORS = (CredentialError, *TRANSPORT_ERRORS)


class ProviderAccount(Protocol):
    id: str

    async def ensure_fresh(
        self, client: httpx.AsyncClient, force: bool = False
    ) -> None: ...


class AllAccountsFailed(Exception):
    def __init__(self, detail: str, status_code: int = 502):
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


class CompletionProvider(ABC):
    """Shared completion workflow with provider-specific request hooks."""

    provider: str
    display_name: str
    retry_unauthorized = False

    def __init__(
        self,
        settings: Settings,
        router: AccountRouter,
        client: httpx.AsyncClient,
    ):
        self.settings = settings
        self.router = router
        self.client = client

    async def open_completion(
        self,
        path: str,
        body: dict[str, Any],
        *,
        context: dict[str, Any] | None = None,
    ) -> tuple[object, httpx.Response]:
        prepared_body = self.prepare_body(body)
        candidates = await self.router.candidates(self.provider)
        last_error = "no attempts made"

        for account in candidates:
            try:
                response = await self._attempt(
                    account, path, prepared_body, context or {}
                )
            except REQUEST_ERRORS as exc:
                last_error = f"{account.id}: {exc}"
                log.warning(
                    "%s request failed on %s: %s",
                    self.display_name,
                    account.id,
                    exc,
                )
                continue

            if response.status_code in RETRYABLE_UPSTREAM_STATUSES:
                if response.status_code == 429:
                    await self.router.record_rate_limited(
                        account, self._retry_after(response)
                    )
                last_error = f"{account.id}: HTTP {response.status_code}"
                await response.aclose()
                continue

            await self.router.record_success(account)
            return account, response

        raise AllAccountsFailed(
            f"all {self.display_name} attempts failed ({last_error})"
        )

    async def _attempt(
        self,
        account: ProviderAccount,
        path: str,
        body: dict[str, Any],
        context: dict[str, Any],
    ) -> httpx.Response:
        attempts = (False, True) if self.retry_unauthorized else (False,)
        response: httpx.Response | None = None

        for force_refresh in attempts:
            await account.ensure_fresh(self.client, force=force_refresh)
            request = self.client.build_request(
                "POST",
                self.url(path),
                headers=self.build_headers(account, body, context),
                json=body,
                timeout=self.settings.request_timeout,
            )
            response = await self.client.send(request, stream=True)
            if response.status_code != 401 or force_refresh:
                return response
            await response.aclose()
            log.info(
                "401 on %s account %s; forcing token refresh",
                self.display_name,
                account.id,
            )

        if response is None:
            raise RuntimeError("provider request produced no response")
        return response

    def prepare_body(self, body: dict[str, Any]) -> dict[str, Any]:
        return dict(body)

    @abstractmethod
    def url(self, path: str) -> str:
        pass

    @abstractmethod
    def build_headers(
        self,
        account: ProviderAccount,
        body: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, str]:
        pass

    @staticmethod
    def _retry_after(response: httpx.Response) -> int | None:
        value = response.headers.get("retry-after")
        try:
            return int(float(value)) if value else None
        except ValueError:
            return None
