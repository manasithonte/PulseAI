import asyncio
import logging
import os
import socket
import time
from datetime import datetime, timezone

import asyncpg
import numpy as np
import redis.asyncio as redis

from .alerts import send_email_alert, send_slack_alert
from .db import insert_alert, insert_metrics_batch
from .features import METRIC_NAMES
from .ml.inference import AnomalyScorer
from .redis_store import RedisRollingWindowStore, try_acquire_alert_cooldown

STREAM_NAME = "metrics_stream"
GROUP_NAME = "metrics_consumer_group"
# Unique per process/replica: two backend containers sharing one Redis
# consumer group must use distinct consumer names, or XPENDING/XCLAIM-based
# recovery and per-consumer monitoring can't tell them apart.
CONSUMER_NAME = os.environ.get("CONSUMER_NAME") or f"backend-{socket.gethostname()}"
BATCH_SIZE = 100
BLOCK_MS = 1000
ANOMALY_SCORES_KEY = "anomaly_scores"
ALERT_COOLDOWN_SECONDS = 30
CRITICAL_THRESHOLD = 0.85
STALE_PENDING_MS = 30_000

logger = logging.getLogger("pulseai.consumer")


async def ensure_group(client: redis.Redis) -> None:
    try:
        await client.xgroup_create(STREAM_NAME, GROUP_NAME, id="0", mkstream=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


def normalize(fields: dict) -> dict:
    ts = float(fields["timestamp"])
    return {
        "node_id": int(fields["node_id"]),
        "cpu": float(fields["cpu"]),
        "memory": float(fields["memory"]),
        "latency_ms": float(fields["latency_ms"]),
        "error_rate": float(fields["error_rate"]),
        "ts": ts,
        "recorded_at": datetime.fromtimestamp(ts, tz=timezone.utc),
    }


def most_deviant_metric(window: list, latest: dict) -> str:
    best_metric, best_z = METRIC_NAMES[0], -1.0
    for metric in METRIC_NAMES:
        values = np.array([m[metric] for m in window], dtype=np.float64)
        std = values.std()
        if std < 1e-9:
            continue
        z = abs((latest[metric] - values.mean()) / std)
        if z > best_z:
            best_metric, best_z = metric, z
    return best_metric


async def _update_and_score_node(
    rolling_store: RedisRollingWindowStore, scorer: AnomalyScorer, node_id: int, rows: list
) -> tuple:
    for row in rows:
        await rolling_store.add(node_id, row, row["ts"])
    window = await rolling_store.window(node_id)
    if window is None:
        return node_id, None
    return node_id, scorer.score(window)


async def run_consumer(
    client: redis.Redis,
    pg_pool: asyncpg.Pool,
    rolling_store: RedisRollingWindowStore,
    scorer: AnomalyScorer,
) -> None:
    await ensure_group(client)
    logger.info("Consumer started, group=%s consumer=%s", GROUP_NAME, CONSUMER_NAME)
    claim_cursor = "0-0"

    while True:
        # Reclaim entries left pending by a replica that died or restarted
        # mid-batch (e.g. crashed after XREADGROUP, before XACK) so they
        # don't sit unprocessed forever under a dead consumer name.
        claim_cursor, claimed, _ = await client.xautoclaim(
            STREAM_NAME, GROUP_NAME, CONSUMER_NAME, min_idle_time=STALE_PENDING_MS, start_id=claim_cursor, count=BATCH_SIZE
        )
        if claimed:
            logger.warning("Reclaimed %d stale pending entries from a dead consumer", len(claimed))
            response = [(STREAM_NAME, claimed)]
        else:
            response = await client.xreadgroup(
                GROUP_NAME, CONSUMER_NAME, {STREAM_NAME: ">"}, count=BATCH_SIZE, block=BLOCK_MS
            )
        if not response:
            continue

        batch = []
        entry_ids = []
        for _stream_key, entries in response:
            for entry_id, fields in entries:
                try:
                    batch.append(normalize(fields))
                except (KeyError, ValueError):
                    logger.warning("Dropping malformed entry %s: %s", entry_id, fields)
                entry_ids.append(entry_id)

        if batch:
            await insert_metrics_batch(pg_pool, batch)

            rows_by_node: dict[int, list] = {}
            for row in batch:
                rows_by_node.setdefault(row["node_id"], []).append(row)

            inference_start = time.monotonic()
            results = await asyncio.gather(
                *(
                    _update_and_score_node(rolling_store, scorer, node_id, rows)
                    for node_id, rows in rows_by_node.items()
                )
            )
            scores = {node_id: score for node_id, score in results if score is not None}
            inference_ms = (time.monotonic() - inference_start) * 1000

            if scores:
                logger.info(
                    "Scored %d nodes in %.1fms (%.2fms/node)",
                    len(scores),
                    inference_ms,
                    inference_ms / len(scores),
                )
                await client.hset(ANOMALY_SCORES_KEY, mapping={str(k): v for k, v in scores.items()})

            for node_id, score in scores.items():
                if score <= scorer.threshold:
                    continue
                if not await try_acquire_alert_cooldown(client, node_id, ALERT_COOLDOWN_SECONDS):
                    continue

                window = await rolling_store.window(node_id)
                latest = await rolling_store.latest_metric_values(node_id)
                metric = most_deviant_metric(window, latest) if window and latest else "unknown"
                severity = "critical" if score > CRITICAL_THRESHOLD else "warning"
                message = f"Node {node_id} anomaly on {metric} (score={score:.2f}, severity={severity})"
                await insert_alert(pg_pool, node_id, metric, score, severity, message)
                logger.warning(message)

                await send_slack_alert(f":rotating_light: {message}")
                if severity == "critical":
                    await send_email_alert(f"PulseAI critical alert: node {node_id}", message)

        if entry_ids:
            await client.xack(STREAM_NAME, GROUP_NAME, *entry_ids)
