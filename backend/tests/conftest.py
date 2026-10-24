import fakeredis
import numpy as np
import pytest

from app.redis_store import RedisRollingWindowStore


def normal_reading(rng: np.random.Generator) -> dict:
    """Matches the simulator's (and training scripts') normal distributions."""
    return {
        "cpu": max(0.0, rng.normal(45, 10)),
        "memory": max(0.0, rng.normal(60, 8)),
        "latency_ms": max(0.0, rng.normal(120, 20)),
        "error_rate": max(0.0, rng.normal(0.02, 0.005)),
    }


def anomaly_reading(rng: np.random.Generator) -> dict:
    return {
        "cpu": max(0.0, rng.normal(92, 4)),
        "memory": max(0.0, rng.normal(88, 5)),
        "latency_ms": max(0.0, rng.normal(750, 80)),
        "error_rate": max(0.0, rng.normal(0.25, 0.05)),
    }


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(0)


@pytest.fixture
def normal_window(rng) -> list:
    """A full 60s window (120 readings at 0.5s) of healthy telemetry."""
    return [normal_reading(rng) for _ in range(120)]


@pytest.fixture
def anomaly_window(rng) -> list:
    return [anomaly_reading(rng) for _ in range(120)]


@pytest.fixture
async def redis_client():
    client = fakeredis.FakeAsyncRedis(decode_responses=True)
    yield client
    await client.flushall()
    await client.aclose()


@pytest.fixture
def rolling_store(redis_client) -> RedisRollingWindowStore:
    return RedisRollingWindowStore(redis_client)
