import pytest

pytestmark = pytest.mark.asyncio


async def test_increment_and_used(quota):
    assert await quota.used_today("x") == 0
    assert await quota.increment("x") == 1
    assert await quota.increment("x") == 2
    assert await quota.used_today("x") == 2


async def test_remaining_with_limit(quota):
    await quota.increment("x")
    await quota.increment("x")
    assert await quota.remaining("x", 10) == 8


async def test_remaining_uncapped_is_none(quota):
    assert await quota.remaining("x", None) is None


async def test_cooldown_lifecycle(quota):
    assert not await quota.is_cooling_down("x")
    await quota.start_cooldown("x", 60)
    assert await quota.is_cooling_down("x")


async def test_snapshot_shape(quota):
    await quota.increment("x")
    snap = await quota.snapshot("x", 10)
    assert snap == {
        "used_today": 1,
        "daily_limit": 10,
        "remaining": 9,
        "cooling_down": False,
    }
