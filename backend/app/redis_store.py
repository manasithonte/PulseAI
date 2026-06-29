import json
from typing import Optional

import redis.asyncio as redis

from .features import METRIC_NAMES, MIN_SAMPLES, WINDOW_SECONDS, compute_features

ROLLING_KEY_PREFIX = "rolling"
COOLDOWN_KEY_PREFIX = "alert_cooldown"


class RedisRollingWindowStore:
    """Redis-backed equivalent of features.RollingWindowStore.

    Keeps the rolling window in a Redis sorted set (score = reading
    timestamp) instead of in-process memory, so multiple backend replicas
    consuming the same Redis Streams consumer group see one consistent
    window per node instead of each replica holding a disjoint partial view.
    """

    def __init__(self, client: redis.Redis, window_seconds: int = WINDOW_SECONDS):
        self.redis = client
        self.window_seconds = window_seconds

    def _key(self, node_id: int) -> str:
        return f"{ROLLING_KEY_PREFIX}:{node_id}"

    async def add(self, node_id: int, metrics: dict, ts: float) -> None:
        member = json.dumps({m: metrics[m] for m in METRIC_NAMES} | {"ts": ts})
        key = self._key(node_id)
        cutoff = ts - self.window_seconds
        pipe = self.redis.pipeline()
        pipe.zadd(key, {member: ts})
        pipe.zremrangebyscore(key, "-inf", cutoff)
        pipe.expire(key, self.window_seconds * 2)
        await pipe.execute()

    async def window(self, node_id: int) -> Optional[list]:
        members = await self.redis.zrange(self._key(node_id), 0, -1)
        if len(members) < MIN_SAMPLES:
            return None
        return [json.loads(m) for m in members]

    async def features(self, node_id: int):
        window = await self.window(node_id)
        if window is None:
            return None
        return compute_features(window)

    async def latest_metric_values(self, node_id: int) -> Optional[dict]:
        latest = await self.redis.zrange(self._key(node_id), -1, -1)
        if not latest:
            return None
        return json.loads(latest[0])


async def try_acquire_alert_cooldown(client: redis.Redis, node_id: int, cooldown_seconds: int) -> bool:
    """Atomically claim the right to raise an alert for this node.

    Returns True if no other replica has alerted for this node within the
    cooldown window, False if one already has. SET NX EX is atomic in Redis,
    so this is safe across concurrent backend replicas without locking.
    """
    key = f"{COOLDOWN_KEY_PREFIX}:{node_id}"
    acquired = await client.set(key, "1", nx=True, ex=cooldown_seconds)
    return bool(acquired)
