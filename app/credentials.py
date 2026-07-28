"""Codex ``auth.json`` accounts: load, refresh, persist.

Each file in ``AUTH_DIR`` becomes a :class:`CodexAccount`. The account holds the
mutable token state, knows when its access token is about to expire, refreshes
it via the OAuth ``refresh_token`` grant, and writes the rotated tokens back to
the same file (matching Codex CLI behavior). Refreshes are serialized per
account with an ``asyncio.Lock`` so concurrent requests don't stampede.
"""

from __future__ import annotations

import asyncio
import copy
import datetime as dt
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Optional

import httpx

from . import jwt_util
from .config import Settings

log = logging.getLogger("gateway.credentials")


class CredentialError(Exception):
    pass


class CodexAccount:
    provider = "codex"

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
        try:
            payload = resp.json()
        except json.JSONDecodeError as exc:
            raise CredentialError(f"token refresh returned invalid JSON for {self.id}") from exc
        access_token = payload.get("access_token") if isinstance(payload, dict) else None
        if not isinstance(access_token, str) or not access_token:
            raise CredentialError(f"token refresh returned no access token for {self.id}")

        # Refresh-token rotation invalidates the old refresh token. Persist the
        # complete replacement before exposing it in memory: otherwise a failed
        # disk write works only until the next restart, then leaves the account
        # permanently unable to refresh.
        updated = copy.deepcopy(self._data)
        tokens = updated.setdefault("tokens", {})
        tokens["access_token"] = access_token
        if payload.get("refresh_token"):
            tokens["refresh_token"] = payload["refresh_token"]
        if payload.get("id_token"):
            tokens["id_token"] = payload["id_token"]
        updated["last_refresh"] = dt.datetime.now(dt.timezone.utc).isoformat(
            timespec="milliseconds"
        ).replace("+00:00", "Z")
        self._persist(updated)
        self._data = updated
        log.info("account %s token refreshed (new exp=%s)", self.id, self.expires_at())

    def _persist(self, data: dict) -> None:
        """Atomically write the updated auth.json back to disk."""
        try:
            _write_auth_json(self.path, data)
        except OSError as exc:
            raise CredentialError(f"could not persist refreshed tokens for {self.id}: {exc}") from exc


class OpenCodeGoAccount:
    """OpenCode Go subscription account backed by a bearer API key."""

    provider = "opencode-go"
    daily_limit: Optional[int] = None

    def __init__(self, path: Optional[Path], data: dict, settings: Settings, acct_id: str = ""):
        self.path = path
        self.id = acct_id or (path.stem if path else "opencode-go")
        self._settings = settings
        self._data = data
        api_key = str(data.get("api_key") or data.get("OPENCODE_GO_API_KEY") or "").strip()
        if not valid_api_key(api_key):
            label = path.name if path else self.id
            raise CredentialError(f"{label}: missing or invalid api_key")
        self._api_key = api_key

    @property
    def access_token(self) -> str:
        return self._api_key

    @property
    def account_id(self) -> Optional[str]:
        return None

    @property
    def plan(self) -> str:
        return "opencode-go"

    def masked_token(self) -> str:
        tok = self.access_token
        return f"{tok[:6]}…{tok[-4:]}" if len(tok) > 12 else "****"

    def expires_at(self) -> Optional[int]:
        return None

    async def ensure_fresh(self, client: httpx.AsyncClient, force: bool = False) -> None:
        return None


class XAIAccount:
    """xAI inference account backed by an API key."""

    provider = "xai"
    daily_limit: Optional[int] = None

    def __init__(self, path: Optional[Path], data: dict, settings: Settings, acct_id: str = ""):
        self.path = path
        self.id = acct_id or (path.stem if path else "xai")
        self._settings = settings
        self._data = data
        api_key = str(data.get("api_key") or data.get("XAI_API_KEY") or "").strip()
        if not valid_api_key(api_key):
            label = path.name if path else self.id
            raise CredentialError(f"{label}: missing or invalid api_key")
        self._api_key = api_key

    @property
    def access_token(self) -> str:
        return self._api_key

    @property
    def account_id(self) -> Optional[str]:
        return None

    @property
    def plan(self) -> str:
        return "xai-api"

    def masked_token(self) -> str:
        tok = self.access_token
        return f"{tok[:6]}…{tok[-4:]}" if len(tok) > 12 else "****"

    def expires_at(self) -> Optional[int]:
        return None

    async def ensure_fresh(self, client: httpx.AsyncClient, force: bool = False) -> None:
        return None


_ACCOUNT_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def valid_account_id(account_id: str) -> bool:
    """Account ids map to filenames, so guard against path traversal etc."""
    return bool(_ACCOUNT_ID_RE.match(account_id)) and account_id not in (".", "..")


def valid_api_key(api_key: str) -> bool:
    """Reject empty, whitespace/control-heavy keys before they reach headers."""
    return 8 <= len(api_key) <= 4096 and not _CONTROL_RE.search(api_key) and not any(
        c.isspace() for c in api_key
    )


def _is_opencode_go(data: dict) -> bool:
    provider = str(data.get("provider") or data.get("type") or "").lower().replace("_", "-")
    return provider == "opencode-go" or "api_key" in data or "OPENCODE_GO_API_KEY" in data


def _is_xai(data: dict) -> bool:
    provider = str(data.get("provider") or data.get("type") or "").lower().replace("_", "-")
    return provider == "xai" or "XAI_API_KEY" in data


def _account_from_data(path: Path, data: dict, settings: Settings):
    if _is_xai(data):
        return XAIAccount(path, data, settings)
    if _is_opencode_go(data):
        return OpenCodeGoAccount(path, data, settings)
    return CodexAccount(path, data, settings)


def _env_opencode_go_accounts(settings: Settings) -> list[OpenCodeGoAccount]:
    accounts: list[OpenCodeGoAccount] = []
    for idx, api_key in enumerate(filter(None, (k.strip() for k in settings.opencode_go_api_keys.split(","))), 1):
        acct_id = f"opencode-go-env-{idx}"
        try:
            accounts.append(OpenCodeGoAccount(None, {"api_key": api_key}, settings, acct_id=acct_id))
        except CredentialError as exc:
            log.error("skipping %s: %s", acct_id, exc)
    return accounts


def _env_xai_accounts(settings: Settings) -> list[XAIAccount]:
    accounts: list[XAIAccount] = []
    for idx, api_key in enumerate(filter(None, (key.strip() for key in settings.xai_api_keys.split(","))), 1):
        acct_id = f"xai-env-{idx}"
        try:
            accounts.append(XAIAccount(None, {"type": "xai", "api_key": api_key}, settings, acct_id=acct_id))
        except CredentialError as exc:
            log.error("skipping %s: %s", acct_id, exc)
    return accounts


def load_accounts(settings: Settings) -> list:
    auth_dir = Path(settings.auth_dir)
    auth_dir.mkdir(parents=True, exist_ok=True)

    accounts = []
    for path in sorted(auth_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text())
            accounts.append(_account_from_data(path, data, settings))
        except (json.JSONDecodeError, CredentialError) as exc:
            log.error("skipping %s: %s", path.name, exc)
    accounts.extend(_env_opencode_go_accounts(settings))
    accounts.extend(_env_xai_accounts(settings))

    if not accounts:
        # Allowed: the gateway can boot empty and have accounts uploaded via the
        # admin API. Requests just 503 until one is added.
        log.warning("no Codex auth files in '%s' — upload one via PUT /admin/accounts/{id}", auth_dir)
    return accounts


def _write_auth_json(path: Path, data: dict) -> None:
    """Durably replace an auth file without ever relaxing its permissions."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
        os.chmod(path, 0o600)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def save_account_file(settings: Settings, account_id: str, data: dict):
    """Validate and atomically write a credential JSON, returning the account."""
    if not valid_account_id(account_id):
        raise CredentialError(f"invalid account id '{account_id}'")
    auth_dir = Path(settings.auth_dir)
    auth_dir.mkdir(parents=True, exist_ok=True)
    path = auth_dir / f"{account_id}.json"
    # Constructing validates the token shape (raises CredentialError if bad).
    account = _account_from_data(path, data, settings)
    _write_auth_json(path, data)
    return account


def delete_account_file(settings: Settings, account_id: str) -> bool:
    if not valid_account_id(account_id):
        return False
    path = Path(settings.auth_dir) / f"{account_id}.json"
    if path.exists():
        path.unlink()
        return True
    return False
