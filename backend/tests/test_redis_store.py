import numpy as np

from app.features import MIN_SAMPLES, RollingWindowStore
from app.redis_store import RedisRollingWindowStore, try_acquire_alert_cooldown


async def test_redis_store_matches_in_memory_store(rolling_store, normal_window):
    memory_store = RollingWindowStore()
    for i, row in enumerate(normal_window):
        await rolling_store.add(1, row, ts=i * 0.5)
        memory_store.add(1, row, ts=i * 0.5)

    np.testing.assert_allclose(await rolling_store.features(1), memory_store.features(1))


async def test_redis_store_requires_min_samples(rolling_store, normal_window):
    for i, row in enumerate(normal_window[: MIN_SAMPLES - 1]):
        await rolling_store.add(1, row, ts=float(i))
    assert await rolling_store.window(1) is None
    assert await rolling_store.features(1) is None


async def test_redis_store_evicts_old_readings(redis_client, normal_window):
    store = RedisRollingWindowStore(redis_client, window_seconds=10)
    for ts, row in enumerate(normal_window[:20]):
        await store.add(1, row, ts=float(ts))

    window = await store.window(1)
    assert [r["ts"] for r in window] == [float(ts) for ts in range(10, 20)]
    assert await redis_client.ttl("rolling:1") > 0


async def test_latest_metric_values(rolling_store, normal_window):
    assert await rolling_store.latest_metric_values(1) is None
    for i, row in enumerate(normal_window[:3]):
        await rolling_store.add(1, row, ts=float(i))

    latest = await rolling_store.latest_metric_values(1)
    assert latest["cpu"] == normal_window[2]["cpu"]
    assert latest["ts"] == 2.0


async def test_alert_cooldown_is_acquired_once(redis_client):
    assert await try_acquire_alert_cooldown(redis_client, 7, cooldown_seconds=30)
    assert not await try_acquire_alert_cooldown(redis_client, 7, cooldown_seconds=30)
    # Cooldowns are per node.
    assert await try_acquire_alert_cooldown(redis_client, 8, cooldown_seconds=30)
    assert 0 < await redis_client.ttl("alert_cooldown:7") <= 30
