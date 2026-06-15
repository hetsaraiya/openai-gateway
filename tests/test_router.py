import pytest

from app.router import AccountRouter, NoAccountAvailable
from tests.conftest import make_settings

pytestmark = pytest.mark.asyncio


async def test_fallback_uses_config_order(quota, three_accounts):
    router = AccountRouter(make_settings("fallback"), three_accounts, quota)
    cands = await router.candidates()
    assert [a.id for a in cands] == ["a", "b", "c"]


async def test_round_robin_rotates(quota, three_accounts):
    router = AccountRouter(make_settings("round_robin"), three_accounts, quota)
    first = (await router.candidates())[0].id
    second = (await router.candidates())[0].id
    third = (await router.candidates())[0].id
    assert {first, second, third} == {"a", "b", "c"}


async def test_quota_aware_prefers_most_remaining(quota, three_accounts):
    # Burn 8 of account "a"'s 10-request budget; "b" still has 10.
    for _ in range(8):
        await quota.increment("a")
    router = AccountRouter(make_settings("quota_aware"), three_accounts, quota)
    cands = await router.candidates()
    # "c" has no cap (sentinel huge), then "b" (10 left), then "a" (2 left).
    assert cands[0].id in {"c", "b"}
    assert cands[-1].id == "a"


async def test_exhausted_account_is_skipped(quota, three_accounts):
    for _ in range(10):
        await quota.increment("a")  # a now at its limit of 10
    router = AccountRouter(make_settings("fallback"), three_accounts, quota)
    ids = [a.id for a in await router.candidates()]
    assert "a" not in ids


async def test_cooldown_account_is_skipped(quota, three_accounts):
    await quota.start_cooldown("a", 60)
    router = AccountRouter(make_settings("fallback"), three_accounts, quota)
    ids = [a.id for a in await router.candidates()]
    assert "a" not in ids


async def test_no_account_available_raises(quota, three_accounts):
    for acct in three_accounts:
        await quota.start_cooldown(acct.id, 60)
    router = AccountRouter(make_settings("fallback"), three_accounts, quota)
    with pytest.raises(NoAccountAvailable):
        await router.candidates()


async def test_max_attempts_caps_candidates(quota, three_accounts):
    settings = make_settings("fallback", max_account_attempts=2)
    router = AccountRouter(settings, three_accounts, quota)
    assert len(await router.candidates()) == 2


async def test_record_rate_limited_sets_cooldown(quota, three_accounts):
    router = AccountRouter(make_settings(), three_accounts, quota)
    await router.record_rate_limited(three_accounts[0], retry_after=30)
    assert await quota.is_cooling_down("a")


async def test_add_and_remove_account(quota, three_accounts):
    from tests.conftest import FakeAccount
    router = AccountRouter(make_settings("fallback"), three_accounts, quota)
    assert {a.id for a in router.accounts()} == {"a", "b", "c"}
    # add new
    assert router.add_account(FakeAccount("d", None)) is False
    assert "d" in {a.id for a in router.accounts()}
    # replace existing returns True
    assert router.add_account(FakeAccount("a", 5)) is True
    assert sum(1 for x in router.accounts() if x.id == "a") == 1
    # remove
    assert router.remove_account("b") is True
    assert "b" not in {a.id for a in router.accounts()}
    assert router.remove_account("nope") is False
