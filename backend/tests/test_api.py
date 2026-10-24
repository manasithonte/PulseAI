import httpx
import pytest

from app.consumer import ANOMALY_SCORES_KEY
from app.main import app


@pytest.fixture
async def client(redis_client, rolling_store):
    # ASGITransport skips the lifespan, so no real Redis/Postgres/consumer
    # starts; wire the fakes onto app.state instead.
    app.state.redis = redis_client
    app.state.rolling_store = rolling_store
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_anomaly_scores(client, redis_client):
    await redis_client.hset(ANOMALY_SCORES_KEY, mapping={"1": 0.12, "2": 0.9})

    resp = await client.get("/anomaly-scores")

    assert resp.status_code == 200
    assert resp.json() == {"1": 0.12, "2": 0.9}
