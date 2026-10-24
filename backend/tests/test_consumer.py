import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from app import consumer
from app.consumer import (
    ANOMALY_SCORES_KEY,
    GROUP_NAME,
    STREAM_NAME,
    most_deviant_metric,
    normalize,
    run_consumer,
)
from app.ml.inference import AnomalyScorer


class MaxCpuScorer(AnomalyScorer):
    """Deterministic stand-in for a real model: score = peak CPU / 100."""

    threshold = 0.6

    def score(self, window: list) -> float:
        return max(r["cpu"] for r in window) / 100


def entry(node_id: int, ts: float, cpu: float = 40.0) -> dict:
    return {
        "node_id": str(node_id),
        "cpu": str(cpu),
        "memory": "60",
        "latency_ms": "120",
        "error_rate": "0.02",
        "timestamp": str(ts),
    }


@pytest.fixture
def sinks(monkeypatch):
    """Replace Postgres writes and outbound alerts with mocks."""
    mocks = {
        "insert_metrics_batch": AsyncMock(),
        "insert_alert": AsyncMock(return_value=1),
        "send_slack_alert": AsyncMock(),
        "send_email_alert": AsyncMock(),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(consumer, name, mock)
    return mocks


async def run_until(redis_client, rolling_store, condition, timeout: float = 5.0):
    """Run the real consumer loop until `condition()` holds, then stop it."""
    task = asyncio.create_task(run_consumer(redis_client, None, rolling_store, MaxCpuScorer()))
    try:
        deadline = time.monotonic() + timeout
        while not await condition():
            if task.done():
                task.result()  # surface the consumer's exception
            if time.monotonic() > deadline:
                raise AssertionError("consumer did not reach expected state in time")
            await asyncio.sleep(0.05)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


async def pending_count(redis_client) -> int:
    return (await redis_client.xpending(STREAM_NAME, GROUP_NAME))["pending"]


def test_normalize_parses_stream_fields():
    row = normalize(entry(3, 1_700_000_000.5, cpu=12.5))
    assert row["node_id"] == 3
    assert row["cpu"] == 12.5
    assert row["recorded_at"].timestamp() == 1_700_000_000.5


def test_most_deviant_metric_picks_largest_z_score():
    window = [{"cpu": 40 + i % 3, "memory": 60 + i % 3, "latency_ms": 120 + i % 3, "error_rate": 0.02} for i in range(30)]
    latest = {"cpu": 41, "memory": 61, "latency_ms": 500, "error_rate": 0.02}
    assert most_deviant_metric(window, latest) == "latency_ms"


async def test_healthy_batch_is_persisted_scored_and_acked(redis_client, rolling_store, sinks):
    for i in range(6):
        await redis_client.xadd(STREAM_NAME, entry(1, ts=i * 0.5))

    async def scored():
        return await redis_client.hget(ANOMALY_SCORES_KEY, "1") is not None

    await run_until(redis_client, rolling_store, scored)

    assert float(await redis_client.hget(ANOMALY_SCORES_KEY, "1")) == pytest.approx(0.4)
    assert sum(len(c.args[1]) for c in sinks["insert_metrics_batch"].await_args_list) == 6
    assert await pending_count(redis_client) == 0
    sinks["insert_alert"].assert_not_awaited()
    sinks["send_slack_alert"].assert_not_awaited()


async def test_anomaly_raises_one_alert_per_cooldown(redis_client, rolling_store, sinks):
    for i in range(5):
        await redis_client.xadd(STREAM_NAME, entry(2, ts=i * 0.5))
    await redis_client.xadd(STREAM_NAME, entry(2, ts=3.0, cpu=95.0))

    async def alerted():
        return sinks["insert_alert"].await_count >= 1

    await run_until(redis_client, rolling_store, alerted)

    # A second spike inside the cooldown window must not alert again.
    await redis_client.xadd(STREAM_NAME, entry(2, ts=3.5, cpu=97.0))

    async def drained():
        return await redis_client.xlen(STREAM_NAME) == 7 and await pending_count(redis_client) == 0 and (
            float(await redis_client.hget(ANOMALY_SCORES_KEY, "2")) == pytest.approx(0.97)
        )

    await run_until(redis_client, rolling_store, drained)

    sinks["insert_alert"].assert_awaited_once()
    _pool, node_id, metric, score, severity, _message = sinks["insert_alert"].await_args.args
    assert (node_id, metric, severity) == (2, "cpu", "critical")
    assert score == pytest.approx(0.95)
    sinks["send_slack_alert"].assert_awaited_once()
    sinks["send_email_alert"].assert_awaited_once()


async def test_warning_alert_skips_email(redis_client, rolling_store, sinks):
    for i in range(5):
        await redis_client.xadd(STREAM_NAME, entry(4, ts=i * 0.5))
    await redis_client.xadd(STREAM_NAME, entry(4, ts=3.0, cpu=70.0))

    async def alerted():
        return sinks["send_slack_alert"].await_count >= 1

    await run_until(redis_client, rolling_store, alerted)

    assert sinks["insert_alert"].await_args.args[4] == "warning"
    sinks["send_email_alert"].assert_not_awaited()


async def test_malformed_entry_is_dropped_but_acked(redis_client, rolling_store, sinks):
    await redis_client.xadd(STREAM_NAME, {"node_id": "1", "cpu": "not-a-number"})
    await redis_client.xadd(STREAM_NAME, entry(1, ts=0.0))

    async def drained():
        return sinks["insert_metrics_batch"].await_count >= 1 and await pending_count(redis_client) == 0

    await run_until(redis_client, rolling_store, drained)

    (batch,) = [c.args[1] for c in sinks["insert_metrics_batch"].await_args_list]
    assert len(batch) == 1


async def test_reclaims_entries_left_pending_by_dead_consumer(redis_client, rolling_store, sinks, monkeypatch):
    await consumer.ensure_group(redis_client)
    for i in range(3):
        await redis_client.xadd(STREAM_NAME, entry(5, ts=float(i)))
    # Another replica reads the entries, then dies before XACK.
    await redis_client.xreadgroup(GROUP_NAME, "dead-replica", {STREAM_NAME: ">"}, count=10)
    assert await pending_count(redis_client) == 3

    monkeypatch.setattr(consumer, "STALE_PENDING_MS", 0)

    async def drained():
        return await pending_count(redis_client) == 0

    await run_until(redis_client, rolling_store, drained)

    assert sum(len(c.args[1]) for c in sinks["insert_metrics_batch"].await_args_list) == 3
