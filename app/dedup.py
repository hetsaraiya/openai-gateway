"""Request deduplication via client ``Idempotency-Key`` headers.

Prevents double-spend when a client retries a request that actually succeeded
upstream (common with flaky networks). Only non-streaming JSON responses are
cached; streaming responses pass through untouched.

State machine per key (Redis):
    SET NX -> we own it, this is the first time. Run the request, then store
              the result under the same key.
    Already "in-flight" -> a concurrent duplicate; caller should wait/return 409.
    Already a cached body -> return it verbatim.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Optional

import redis.asyncio as aioredis

log = logging.getLogger("gateway.dedup")

_INFLIGHT = "__inflight__"


@dataclass
class CachedResponse:
    status_code: int
    body: bytes
    account_id: str


class DedupStore:
    def __init__(self, redis_url: str, ttl: int):
        self._redis = aioredis.from_url(redis_url, decode_responses=False)
        self._ttl = ttl

    async def close(self) -> None:
        try:
            await self._redis.aclose()
        except Exception:  # noqa: BLE001
            pass

    @staticmethod
    def _key(idempotency_key: str) -> bytes:
        return f"gw:idem:{idempotency_key}".encode()

    async def begin(self, idempotency_key: str) -> Optional[CachedResponse]:
        """Try to claim the key.

        Returns ``None`` if we now own the slot (caller proceeds with the
        request). Returns a :class:`CachedResponse` if a completed result is
        already cached. Raises :class:`DuplicateInFlight` if another request
        with the same key is currently running.
        """
        key = self._key(idempotency_key)
        try:
            claimed = await self._redis.set(key, _INFLIGHT.encode(), nx=True, ex=self._ttl)
        except Exception as exc:  # noqa: BLE001
            log.warning("dedup unavailable (%s); proceeding without it", exc)
            return None

        if claimed:
            return None

        existing = await self._redis.get(key)
        if existing == _INFLIGHT.encode():
            raise DuplicateInFlight(idempotency_key)

        try:
            payload = json.loads(existing)
            return CachedResponse(
                status_code=payload["status_code"],
                body=payload["body"].encode("latin-1"),
                account_id=payload["account_id"],
            )
        except Exception:  # noqa: BLE001
            # Corrupt/legacy value — drop it and let the caller proceed.
            await self._redis.delete(key)
            return None

    async def complete(
        self, idempotency_key: str, status_code: int, body: bytes, account_id: str
    ) -> None:
        key = self._key(idempotency_key)
        payload = json.dumps(
            {
                "status_code": status_code,
                "body": body.decode("latin-1"),
                "account_id": account_id,
            }
        ).encode()
        try:
            await self._redis.set(key, payload, ex=self._ttl)
        except Exception as exc:  # noqa: BLE001
            log.warning("could not cache idempotent result: %s", exc)

    async def release(self, idempotency_key: str) -> None:
        """Drop the in-flight marker (e.g. the request failed)."""
        try:
            await self._redis.delete(self._key(idempotency_key))
        except Exception:  # noqa: BLE001
            pass


class DuplicateInFlight(Exception):
    def __init__(self, key: str):
        super().__init__(f"a request with Idempotency-Key '{key}' is already in flight")
        self.key = key
