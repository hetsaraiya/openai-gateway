"""Supported Cursor subscription integration through Cursor Agent CLI."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from .credentials import save_account_file

_ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_LOGIN_URL_RE = re.compile(r"https://cursor\.com/loginDeepControl\?[^\s]+")
_MODEL_RE = re.compile(r"^(\S+)\s+-\s+(.+?)(?:\s+\((?:current|default)[^)]*\))?$")


@dataclass
class CursorLogin:
    id: str
    account_id: str
    home: Path
    process: asyncio.subprocess.Process
    status: str = "starting"
    provider: str = "cursor"
    verification_url: str | None = None
    user_code: str | None = None
    error: str | None = None
    ready: asyncio.Event = field(default_factory=asyncio.Event, repr=False)


class CursorLoginManager:
    def __init__(self, settings, router):
        self._settings = settings
        self._router = router
        self._logins: dict[str, CursorLogin] = {}

    async def start(self, account_id: str) -> CursorLogin:
        login_id = uuid4().hex
        home = Path(self._settings.auth_dir) / ".cursor-accounts" / f"{account_id}-{login_id}"
        home.mkdir(parents=True, mode=0o700)
        process = await asyncio.create_subprocess_exec(
            "env",
            f"HOME={home}",
            "NO_OPEN_BROWSER=1",
            self._settings.cursor_binary,
            "login",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        login = CursorLogin(login_id, account_id, home, process)
        self._logins[login_id] = login
        asyncio.create_task(self._watch(login))
        try:
            await asyncio.wait_for(login.ready.wait(), timeout=15)
        except TimeoutError:
            login.status, login.error = "failed", "Cursor did not return a sign-in URL"
        return login

    async def _watch(self, login: CursorLogin) -> None:
        output = ""
        assert login.process.stdout
        async for raw in login.process.stdout:
            output += _ANSI_RE.sub("", raw.decode(errors="replace"))
            if not login.verification_url:
                match = _LOGIN_URL_RE.search(output)
                if match:
                    login.verification_url = match.group(0)
                    login.status = "pending"
                    login.ready.set()
        result = await login.process.wait()
        if result != 0:
            login.status = "failed"
            login.error = "Cursor sign-in was cancelled or expired"
            login.ready.set()
            return
        try:
            status = await cursor_status(self._settings, login.home)
            user_info = status.get("userInfo") or {}
            data = {
                "type": "cursor-cli",
                "home": login.home.name,
                "email": user_info.get("email"),
                "user_id": user_info.get("userId"),
            }
            account = save_account_file(self._settings, login.account_id, data)
            self._router.add_account(account)
            login.status = "complete"
        except Exception as exc:  # noqa: BLE001
            login.status, login.error = "failed", str(exc)
        finally:
            login.ready.set()

    def get(self, login_id: str) -> CursorLogin | None:
        return self._logins.get(login_id)

    async def close(self) -> None:
        for login in self._logins.values():
            if login.process.returncode is None:
                login.process.terminate()


async def cursor_status(settings, home: Path) -> dict:
    process = await asyncio.create_subprocess_exec(
        "env", f"HOME={home}", settings.cursor_binary, "status", "--format", "json",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(stderr.decode(errors="replace").strip() or "Cursor session is invalid")
    payload = json.loads(stdout)
    if not payload.get("isAuthenticated"):
        raise RuntimeError("Cursor session is not authenticated")
    return payload


async def cursor_models(settings, account) -> list[dict]:
    process = await asyncio.create_subprocess_exec(
        "env", f"HOME={account.home}", settings.cursor_binary, "models",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(stderr.decode(errors="replace").strip() or "Could not list Cursor models")
    models = []
    for raw_line in _ANSI_RE.sub("", stdout.decode(errors="replace")).splitlines():
        match = _MODEL_RE.match(raw_line.strip())
        if match:
            models.append({
                "id": f"cursor/{match.group(1)}",
                "object": "model",
                "created": 0,
                "owned_by": "cursor",
                "display_name": match.group(2),
                "gateway": "cursor",
                "supported_in_api": True,
                "supported_endpoints": ["/v1/chat/completions", "/v1/responses"],
                "prompt_caching": True,
            })
    return models


def cursor_prompt_from_chat(messages: list[dict]) -> str:
    parts = []
    for message in messages:
        role = str(message.get("role") or "user").upper()
        content = message.get("content")
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        parts.append(f"{role}: {text}")
    return "\n\n".join(parts)


def cursor_prompt_from_responses(value) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


async def start_cursor_run(settings, account, model: str, prompt: str, stream: bool):
    workspace = account.home / "workspace"
    workspace.mkdir(mode=0o700, exist_ok=True)
    args = [
        "env", f"HOME={account.home}", settings.cursor_binary,
        "--print", "--output-format", "stream-json" if stream else "json",
        "--mode", "ask", "--trust", "--workspace", str(workspace),
        "--model", model, "--", prompt,
    ]
    return await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL if stream else asyncio.subprocess.PIPE,
    )
