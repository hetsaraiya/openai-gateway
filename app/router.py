"""Account router — decides which upstream account handles each request.

Strategies:
    round_robin   Rotate through accounts evenly.
    quota_aware   Prefer the account with the most remaining daily quota.
    fallback      Stable priority order (config order); the proxy advances to
                  the next candidate when one fails. (default)

All strategies skip accounts that are in 429 cooldown or have exhausted their
daily limit, and all of them yield an ordered candidate list so the proxy can
fall through to the next account on failure.
"""

from __future__ import annotations

import itertools
import logging
from typing import Optional, Sequence

from .config import Settings
from .quota import QuotaStore

log = logging.getLogger("gateway.router")


class NoAccountAvailable(Exception):
    """Raised when every account is exhausted or cooling down."""


class AccountRouter:
    def __init__(self, settings: Settings, accounts: Sequence, quota: QuotaStore):
        self._settings = settings
        self._quota = quota
        self._accounts = list(accounts)
        self._rr = itertools.cycle(range(len(self._accounts)))

    async def _is_available(self, acct) -> bool:
        if await self._quota.is_cooling_down(acct.id):
            return False
        remaining = await self._quota.remaining(acct.id, acct.daily_limit)
        if remaining is not None and remaining <= 0:
            return False
        return True

    async def candidates(self, provider: Optional[str] = None) -> list:
        """Ordered list of accounts to try for one request (best first)."""
        accounts = [
            a for a in self._accounts
            if provider is None or getattr(a, "provider", "codex") == provider
        ]
        available = [a for a in accounts if await self._is_available(a)]
        if not available:
            if provider:
                raise NoAccountAvailable(
                    f"all {provider} accounts are rate-limited or over their daily quota"
                )
            raise NoAccountAvailable(
                "all accounts are rate-limited or over their daily quota"
            )

        strategy = self._settings.strategy
        if strategy == "round_robin":
            ordered = self._round_robin_order(available)
        elif strategy == "quota_aware":
            ordered = await self._quota_aware_order(available)
        else:  # fallback / default — config order
            ordered = available

        return ordered[: self._settings.max_account_attempts]

    def _round_robin_order(self, available: list) -> list:
        # Start at the next cursor position, then wrap, keeping only available ones.
        start = next(self._rr)
        n = len(self._accounts)
        rotated = [self._accounts[(start + i) % n] for i in range(n)]
        avail_ids = {a.id for a in available}
        return [a for a in rotated if a.id in avail_ids]

    async def _quota_aware_order(self, available: list) -> list:
        # Accounts with no cap sort last among ties only by a large sentinel so
        # capped accounts with real headroom are still comparable.
        async def remaining(a) -> int:
            r = await self._quota.remaining(a.id, a.daily_limit)
            return r if r is not None else 10**9

        scored = [(await remaining(a), a) for a in available]
        scored.sort(key=lambda t: t[0], reverse=True)
        return [a for _, a in scored]

    def accounts(self) -> list:
        return list(self._accounts)

    def add_account(self, acct) -> bool:
        """Add or replace an account by id. Returns True if it replaced one."""
        existed = any(a.id == acct.id for a in self._accounts)
        self._accounts = [a for a in self._accounts if a.id != acct.id] + [acct]
        self._rr = itertools.cycle(range(len(self._accounts)))
        return existed

    def remove_account(self, account_id: str) -> bool:
        before = len(self._accounts)
        self._accounts = [a for a in self._accounts if a.id != account_id]
        self._rr = itertools.cycle(range(max(1, len(self._accounts))))
        return len(self._accounts) < before

    async def record_success(self, acct) -> None:
        await self._quota.increment(acct.id)

    async def record_rate_limited(self, acct, retry_after: Optional[int]) -> None:
        cooldown = retry_after or self._settings.rate_limit_cooldown
        await self._quota.start_cooldown(acct.id, cooldown)
