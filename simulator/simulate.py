import asyncio
import os
import random
import time

import redis.asyncio as redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
NODE_COUNT = int(os.environ.get("NODE_COUNT", "50"))
PUBLISH_INTERVAL = float(os.environ.get("PUBLISH_INTERVAL_SECONDS", "0.5"))
STREAM_NAME = os.environ.get("STREAM_NAME", "metrics_stream")
ANOMALY_PROBABILITY = float(os.environ.get("ANOMALY_PROBABILITY", "0.001"))
ANOMALY_DURATION_TICKS = int(os.environ.get("ANOMALY_DURATION_TICKS", "10"))


async def simulate_node(client: redis.Redis, node_id: int) -> None:
    anomaly_ticks_remaining = 0
    while True:
        if anomaly_ticks_remaining == 0 and random.random() < ANOMALY_PROBABILITY:
            anomaly_ticks_remaining = ANOMALY_DURATION_TICKS

        if anomaly_ticks_remaining > 0:
            cpu = random.gauss(92, 4)
            memory = random.gauss(88, 5)
            latency_ms = random.gauss(750, 80)
            error_rate = random.gauss(0.25, 0.05)
            anomaly_ticks_remaining -= 1
        else:
            cpu = random.gauss(45, 10)
            memory = random.gauss(60, 8)
            latency_ms = random.gauss(120, 20)
            error_rate = random.gauss(0.02, 0.005)

        metrics = {
            "node_id": str(node_id),
            "cpu": max(0.0, cpu),
            "memory": max(0.0, memory),
            "latency_ms": max(0.0, latency_ms),
            "error_rate": max(0.0, error_rate),
            "timestamp": time.time(),
        }
        await client.xadd(STREAM_NAME, metrics)
        await asyncio.sleep(PUBLISH_INTERVAL)


async def main() -> None:
    client = redis.from_url(REDIS_URL, decode_responses=True)
    try:
        await client.ping()
        print(f"Connected to Redis at {REDIS_URL}, simulating {NODE_COUNT} nodes...")
        await asyncio.gather(*[simulate_node(client, i) for i in range(NODE_COUNT)])
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
