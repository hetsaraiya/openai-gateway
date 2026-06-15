"""Redis-backed per-account quota and rate-limit state.

Keys (all namespaced under ``gw:``):
    gw:usage:{account_id}:{utc_date}   -> integer counter, expires end of day
    gw:cooldown:{account_id}           -> present while an account is in 429 cooldown

The store degrades gracefully: if Redis is unreachable, quota checks return
"plenty of room" and cooldowns are treated as absent, so the gateway keeps
serving traffic (just without cross-process quota coordination).
"""

from __future__ import annotations

import datetime as dt
import logging
from typing import Optional

import redis.asyncio as aioredis

log = logging.getLogger("gateway.quota")


def _utc_date() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def _seconds_until_utc_midnight() -> int:
    now = dt.datetime.now(dt.timezone.utc)
    tomorrow = (now + dt.timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return max(1, int((tomorrow - now).total_seconds()))


class QuotaStore:
    def __init__(self, redis_url: str):
        self._redis = aioredis.from_url(redis_url, decode_responses=True)

    async def ping(self) -> bool:
        try:
            return bool(await self._redis.ping())
        except Exception:  # noqa: BLE001
            return False

    async def close(self) -> None:
        try:
            await self._redis.aclose()
        except Exception:  # noqa: BLE001
            pass

    def _usage_key(self, account_id: str) -> str:
        return f"gw:usage:{account_id}:{_utc_date()}"

    def _cooldown_key(self, account_id: str) -> str:
        return f"gw:cooldown:{account_id}"

    async def used_today(self, account_id: str) -> int:
        try:
            val = await self._redis.get(self._usage_key(account_id))
            return int(val) if val else 0
        except Exception:  # noqa: BLE001
            return 0

    async def remaining(self, account_id: str, daily_limit: Optional[int]) -> Optional[int]:
        """Remaining requests today, or ``None`` if the account has no cap."""
        if daily_limit is None:
            return None
        return max(0, daily_limit - await self.used_today(account_id))

    async def increment(self, account_id: str) -> int:
        """Count one request against the account. Returns the new daily total."""
        try:
            key = self._usage_key(account_id)
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.incr(key)
                pipe.expire(key, _seconds_until_utc_midnight())
                result = await pipe.execute()
            return int(result[0])
        except Exception as exc:  # noqa: BLE001
            log.warning("quota increment failed for %s: %s", account_id, exc)
            return 0

    async def is_cooling_down(self, account_id: str) -> bool:
        try:
            return bool(await self._redis.exists(self._cooldown_key(account_id)))
        except Exception:  # noqa: BLE001
            return False

    async def start_cooldown(self, account_id: str, seconds: int) -> None:
        try:
            await self._redis.set(self._cooldown_key(account_id), "1", ex=max(1, seconds))
            log.info("account %s in cooldown for %ss", account_id, seconds)
        except Exception as exc:  # noqa: BLE001
            log.warning("could not set cooldown for %s: %s", account_id, exc)

    async def snapshot(self, account_id: str, daily_limit: Optional[int]) -> dict:
        return {
            "used_today": await self.used_today(account_id),
            "daily_limit": daily_limit,
            "remaining": await self.remaining(account_id, daily_limit),
            "cooling_down": await self.is_cooling_down(account_id),
        }
