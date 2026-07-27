from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from .credentials import save_account_file

_URL_RE = re.compile(r"https://auth\.openai\.com/codex/device")
_CODE_RE = re.compile(r"\b[A-Z0-9]{4,8}-[A-Z0-9]{4,8}\b")


@dataclass
class DeviceLogin:
    id: str
    account_id: str
    home: Path
    process: asyncio.subprocess.Process
    status: str = "starting"
    verification_url: str | None = None
    user_code: str | None = None
    error: str | None = None
    ready: asyncio.Event = field(default_factory=asyncio.Event)


class DeviceLoginManager:
    def __init__(self, settings, router):
        self._settings = settings
        self._router = router
        self._logins: dict[str, DeviceLogin] = {}

    async def start(self, account_id: str) -> DeviceLogin:
        login_id = uuid4().hex
        home = Path(self._settings.auth_dir) / ".login-sessions" / login_id
        home.mkdir(parents=True, mode=0o700)
        process = await asyncio.create_subprocess_exec(
            "env", f"CODEX_HOME={home}", self._settings.codex_binary, "login", "--device-auth",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        )
        login = DeviceLogin(login_id, account_id, home, process)
        self._logins[login_id] = login
        asyncio.create_task(self._watch(login))
        try:
            await asyncio.wait_for(login.ready.wait(), timeout=15)
        except TimeoutError:
            login.status, login.error = "failed", "Codex did not return a device code"
        return login

    async def _watch(self, login: DeviceLogin) -> None:
        output = ""
        assert login.process.stdout
        async for raw in login.process.stdout:
            output += re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", raw.decode(errors="replace"))
            if not login.user_code:
                code = _CODE_RE.search(output)
                if code:
                    login.verification_url = _URL_RE.search(output).group(0) if _URL_RE.search(output) else None
                    login.user_code = code.group(0)
                    login.status = "pending"
                    login.ready.set()
        result = await login.process.wait()
        if login.status == "failed":
            return
        if result != 0:
            login.status, login.error = "failed", "Device login was cancelled or expired"
            login.ready.set()
            return
        try:
            data = json.loads((login.home / "auth.json").read_text())
            account = save_account_file(self._settings, login.account_id, data)
            self._router.add_account(account)
            login.status = "complete"
        except Exception as exc:  # noqa: BLE001
            login.status, login.error = "failed", str(exc)
        finally:
            login.ready.set()

    def get(self, login_id: str) -> DeviceLogin | None:
        return self._logins.get(login_id)

    async def close(self) -> None:
        for login in self._logins.values():
            if login.process.returncode is None:
                login.process.terminate()
