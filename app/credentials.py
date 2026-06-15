"""Codex ``auth.json`` accounts: load, refresh, persist.

Each file in ``AUTH_DIR`` becomes a :class:`CodexAccount`. The account holds the
mutable token state, knows when its access token is about to expire, refreshes
it via the OAuth ``refresh_token`` grant, and writes the rotated tokens back to
the same file (matching Codex CLI behavior). Refreshes are serialized per
account with an ``asyncio.Lock`` so concurrent requests don't stampede.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

import httpx

from . import jwt_util
from .config import Settings

log = logging.getLogger("gateway.credentials")


class CredentialError(Exception):
    pass


class CodexAccount:
    def __init__(self, path: Path, data: dict, settings: Settings):
        self.path = path
        self.id = path.stem
        self._settings = settings
        self._data = data
        self._lock = asyncio.Lock()
        # No gateway-side daily cap for subscription accounts (limits are
        # enforced upstream); kept for router compatibility.
        self.daily_limit: Optional[int] = None

        tokens = data.get("tokens") or {}
        if not tokens.get("access_token"):
            raise CredentialError(f"{path.name}: missing tokens.access_token")
        if not tokens.get("refresh_token"):
            raise CredentialError(f"{path.name}: missing tokens.refresh_token")

    # --- token accessors ---------------------------------------------------- #

    @property
    def _tokens(self) -> dict:
        return self._data.setdefault("tokens", {})

    @property
    def access_token(self) -> str:
        return self._tokens["access_token"]

    @property
    def refresh_token(self) -> str:
        return self._tokens["refresh_token"]

    @property
    def account_id(self) -> Optional[str]:
        # Prefer the explicit field; fall back to the id_token claim.
        acc = self._tokens.get("account_id")
        if acc:
            return acc
        id_token = self._tokens.get("id_token")
        return jwt_util.chatgpt_account_id(id_token) if id_token else None

    @property
    def plan(self) -> Optional[str]:
        id_token = self._tokens.get("id_token")
        return jwt_util.chatgpt_plan(id_token) if id_token else None

    def masked_token(self) -> str:
        tok = self.access_token
        return f"{tok[:6]}…{tok[-4:]}" if len(tok) > 12 else "****"

    def _is_expired(self) -> bool:
        exp = jwt_util.expiry(self.access_token)
        if exp is None:
            return False  # can't tell; assume usable, upstream 401 will tell us
        return time.time() >= (exp - self._settings.token_refresh_skew)

    def expires_at(self) -> Optional[int]:
        return jwt_util.expiry(self.access_token)

    # --- refresh ------------------------------------------------------------ #

    async def ensure_fresh(self, client: httpx.AsyncClient, force: bool = False) -> None:
        if not (force or self._is_expired()):
            return
        async with self._lock:
            # Re-check inside the lock: another coroutine may have just refreshed.
            if not force and not self._is_expired():
                return
            await self._refresh(client)

    async def _refresh(self, client: httpx.AsyncClient) -> None:
        log.info("refreshing access token for account %s", self.id)
        resp = await client.post(
            self._settings.oauth_token_url,
            json={
                "client_id": self._settings.oauth_client_id,
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "scope": "openid profile email",
            },
            headers={"Content-Type": "application/json"},
            timeout=30.0,
        )
        if resp.status_code != 200:
            raise CredentialError(
                f"token refresh failed for {self.id}: HTTP {resp.status_code} {resp.text[:200]}"
            )
        payload = resp.json()
        tokens = self._tokens
        tokens["access_token"] = payload["access_token"]
        if payload.get("refresh_token"):
            tokens["refresh_token"] = payload["refresh_token"]
        if payload.get("id_token"):
            tokens["id_token"] = payload["id_token"]
        self._data["last_refresh"] = dt.datetime.now(dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )
        self._persist()
        log.info("account %s token refreshed (new exp=%s)", self.id, self.expires_at())

    def _persist(self) -> None:
        """Atomically write the updated auth.json back to disk."""
        tmp = self.path.with_suffix(".json.tmp")
        try:
            tmp.write_text(json.dumps(self._data, indent=2))
            os.replace(tmp, self.path)
        except Exception as exc:  # noqa: BLE001
            log.warning("could not persist refreshed tokens for %s: %s", self.id, exc)
            tmp.unlink(missing_ok=True)


_ACCOUNT_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def valid_account_id(account_id: str) -> bool:
    """Account ids map to filenames, so guard against path traversal etc."""
    return bool(_ACCOUNT_ID_RE.match(account_id)) and account_id not in (".", "..")


def load_accounts(settings: Settings) -> list[CodexAccount]:
    auth_dir = Path(settings.auth_dir)
    auth_dir.mkdir(parents=True, exist_ok=True)

    accounts: list[CodexAccount] = []
    for path in sorted(auth_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            accounts.append(CodexAccount(path, data, settings))
        except (json.JSONDecodeError, CredentialError) as exc:
            log.error("skipping %s: %s", path.name, exc)

    if not accounts:
        # Allowed: the gateway can boot empty and have accounts uploaded via the
        # admin API. Requests just 503 until one is added.
        log.warning("no Codex auth files in '%s' — upload one via PUT /admin/accounts/{id}", auth_dir)
    return accounts


def save_account_file(settings: Settings, account_id: str, data: dict) -> CodexAccount:
    """Validate and atomically write a Codex auth.json, returning the account."""
    if not valid_account_id(account_id):
        raise CredentialError(f"invalid account id '{account_id}'")
    auth_dir = Path(settings.auth_dir)
    auth_dir.mkdir(parents=True, exist_ok=True)
    path = auth_dir / f"{account_id}.json"
    # Constructing validates the token shape (raises CredentialError if bad).
    account = CodexAccount(path, data, settings)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return account


def delete_account_file(settings: Settings, account_id: str) -> bool:
    if not valid_account_id(account_id):
        return False
    path = Path(settings.auth_dir) / f"{account_id}.json"
    if path.exists():
        path.unlink()
        return True
    return False
