"""Master-key authentication for gateway clients.

Clients authenticate to the *gateway* with the master key (just like they would
authenticate to OpenAI), via either ``Authorization: Bearer <key>`` or the
``X-Gateway-Key`` header. The gateway then substitutes a real account key
upstream. Comparison is constant-time to avoid timing oracles.
"""

from __future__ import annotations

import hmac

from fastapi import Header, HTTPException, status
from typing import Optional

from .config import get_settings


def _extract(authorization: Optional[str], x_gateway_key: Optional[str]) -> Optional[str]:
    if x_gateway_key:
        return x_gateway_key.strip()
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


async def require_master_key(
    authorization: Optional[str] = Header(default=None),
    x_gateway_key: Optional[str] = Header(default=None, alias="X-Gateway-Key"),
) -> None:
    presented = _extract(authorization, x_gateway_key)
    expected = get_settings().master_api_key
    if not presented or not hmac.compare_digest(presented, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error": {
                    "message": "Invalid gateway API key.",
                    "type": "invalid_request_error",
                    "code": "invalid_api_key",
                }
            },
            headers={"WWW-Authenticate": "Bearer"},
        )
