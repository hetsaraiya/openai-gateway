"""Minimal JWT payload reader.

We never *verify* these tokens (OpenAI's backend does that) — we only need to
read public claims like ``exp`` and the ChatGPT account id, so a plain
base64url-decode of the payload segment is sufficient and dependency-free.
"""

from __future__ import annotations

import base64
import json
from typing import Any, Optional


def decode_payload(token: str) -> dict[str, Any]:
    try:
        payload_b64 = token.split(".")[1]
    except IndexError:
        return {}
    padding = "=" * (-len(payload_b64) % 4)
    try:
        raw = base64.urlsafe_b64decode(payload_b64 + padding)
        return json.loads(raw)
    except Exception:  # noqa: BLE001
        return {}


def expiry(token: str) -> Optional[int]:
    """Unix expiry (``exp``) of a JWT access token, or ``None`` if unknown."""
    exp = decode_payload(token).get("exp")
    return int(exp) if isinstance(exp, (int, float)) else None


def chatgpt_account_id(id_token: str) -> Optional[str]:
    """ChatGPT account id from an ``id_token``'s OpenAI auth claim."""
    claims = decode_payload(id_token)
    auth = claims.get("https://api.openai.com/auth")
    if isinstance(auth, dict):
        return auth.get("chatgpt_account_id")
    return None


def chatgpt_plan(id_token: str) -> Optional[str]:
    claims = decode_payload(id_token)
    auth = claims.get("https://api.openai.com/auth")
    if isinstance(auth, dict):
        return auth.get("chatgpt_plan_type")
    return None
