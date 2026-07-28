"""xAI OAuth device login for Grok subscription accounts."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from urllib.parse import urlparse
from uuid import uuid4

import httpx

from . import jwt_util
from .credentials import save_account_file

DEVICE_GRANT = "urn:ietf:params:oauth:grant-type:device_code"


@dataclass
class XAILogin:
    id: str
    account_id: str
    device_code: str
    interval: int
    expires_at: float
    status: str = "pending"
    provider: str = "xai"
    verification_url: str | None = None
    user_code: str | None = None
    error: str | None = None
    task: asyncio.Task | None = field(default=None, repr=False)


class XAILoginManager:
    def __init__(self, settings, router, client: httpx.AsyncClient):
        self._settings = settings
        self._router = router
        self._client = client
        self._logins: dict[str, XAILogin] = {}

    def _headers(self) -> dict[str, str]:
        return {
            "x-grok-client-version": self._settings.grok_client_version,
            "x-grok-client-surface": "headless",
        }

    async def start(self, account_id: str) -> XAILogin:
        response = await self._client.post(
            f"{self._settings.xai_oauth_issuer}/oauth2/device/code",
            data={
                "client_id": self._settings.xai_oauth_client_id,
                "scope": self._settings.xai_oauth_scopes,
                "referrer": "grok-build",
            },
            headers=self._headers(),
            timeout=30.0,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"xAI device login failed (HTTP {response.status_code}): {response.text[:200]}"
            )
        payload = response.json()
        verification_url = (
            payload.get("verification_uri_complete") or payload.get("verification_uri")
        )
        parsed_url = urlparse(verification_url) if isinstance(verification_url, str) else None
        if not (
            parsed_url
            and parsed_url.scheme == "https"
            and parsed_url.hostname in {"auth.x.ai", "accounts.x.ai"}
        ):
            raise RuntimeError("xAI returned an invalid verification URL")

        login = XAILogin(
            id=uuid4().hex,
            account_id=account_id,
            device_code=str(payload["device_code"]),
            interval=max(1, int(payload.get("interval") or 5)),
            expires_at=time.time() + max(1, int(payload.get("expires_in") or 900)),
            verification_url=verification_url,
            user_code=str(payload["user_code"]),
        )
        self._logins[login.id] = login
        login.task = asyncio.create_task(self._poll(login))
        return login

    async def _poll(self, login: XAILogin) -> None:
        interval = login.interval
        token_url = f"{self._settings.xai_oauth_issuer}/oauth2/token"
        while time.time() < login.expires_at:
            await asyncio.sleep(interval)
            try:
                response = await self._client.post(
                    token_url,
                    data={
                        "grant_type": DEVICE_GRANT,
                        "device_code": login.device_code,
                        "client_id": self._settings.xai_oauth_client_id,
                    },
                    headers=self._headers(),
                    timeout=30.0,
                )
                payload = response.json()
            except (httpx.HTTPError, ValueError) as exc:
                login.status, login.error = "failed", f"xAI token exchange failed: {exc}"
                return

            if response.status_code == 200:
                try:
                    self._complete(login, payload, token_url)
                except Exception as exc:  # noqa: BLE001
                    login.status, login.error = "failed", str(exc)
                return

            error = payload.get("error") if isinstance(payload, dict) else None
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval += 5
                continue
            if error == "access_denied":
                login.status, login.error = "failed", "Authorization was denied"
                return
            if error == "expired_token":
                break
            detail = payload.get("error_description") if isinstance(payload, dict) else None
            login.status, login.error = "failed", detail or error or "xAI token exchange failed"
            return

        login.status, login.error = "failed", "The xAI device code expired"

    def _complete(self, login: XAILogin, payload: dict, token_url: str) -> None:
        access_token = payload.get("access_token")
        refresh_token = payload.get("refresh_token")
        if not access_token or not refresh_token:
            raise RuntimeError("xAI OAuth did not return refreshable credentials")
        id_token = payload.get("id_token")
        claims = jwt_util.decode_payload(id_token) if id_token else {}
        expires_in = payload.get("expires_in")
        data = {
            "type": "xai-oauth",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "id_token": id_token,
            "expires_at": (
                int(time.time()) + int(expires_in)
                if isinstance(expires_in, (int, float))
                else jwt_util.expiry(access_token)
            ),
            "user_id": claims.get("sub"),
            "email": claims.get("email"),
            "issuer": self._settings.xai_oauth_issuer,
            "client_id": self._settings.xai_oauth_client_id,
            "token_endpoint": token_url,
            "scope": payload.get("scope") or self._settings.xai_oauth_scopes,
        }
        account = save_account_file(self._settings, login.account_id, data)
        self._router.add_account(account)
        login.status = "complete"

    def get(self, login_id: str) -> XAILogin | None:
        return self._logins.get(login_id)

    async def close(self) -> None:
        tasks = [login.task for login in self._logins.values() if login.task and not login.task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
