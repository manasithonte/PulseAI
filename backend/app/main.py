import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

import redis.asyncio as redis
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .consumer import ANOMALY_SCORES_KEY, run_consumer
from .db import create_pool, fetch_alerts
from .ml.inference import load_scorer
from .redis_store import RedisRollingWindowStore

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
MODEL_TYPE = os.environ.get("MODEL_TYPE", "isolation_forest")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = redis.from_url(REDIS_URL, decode_responses=True)
    app.state.pg_pool = await create_pool()
    app.state.rolling_store = RedisRollingWindowStore(app.state.redis)
    app.state.scorer = load_scorer(MODEL_TYPE)
    app.state.consumer_task = asyncio.create_task(
        run_consumer(app.state.redis, app.state.pg_pool, app.state.rolling_store, app.state.scorer)
    )
    yield
    app.state.consumer_task.cancel()
    await app.state.redis.close()
    await app.state.pg_pool.close()


app = FastAPI(title="PulseAI", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics/latest")
async def latest_metrics(node_id: Optional[int] = None, limit: int = 50):
    pool = app.state.pg_pool
    async with pool.acquire() as conn:
        if node_id is not None:
            rows = await conn.fetch(
                "SELECT node_id, cpu, memory, latency_ms, error_rate, recorded_at "
                "FROM raw_metrics WHERE node_id = $1 ORDER BY recorded_at DESC LIMIT $2",
                node_id,
                limit,
            )
        else:
            rows = await conn.fetch(
                "SELECT node_id, cpu, memory, latency_ms, error_rate, recorded_at "
                "FROM raw_metrics ORDER BY recorded_at DESC LIMIT $1",
                limit,
            )
    return [dict(r) for r in rows]


@app.get("/nodes")
async def nodes():
    pool = app.state.pg_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT DISTINCT node_id FROM raw_metrics ORDER BY node_id")
    return [r["node_id"] for r in rows]


@app.get("/alerts")
async def alerts(limit: int = 100):
    return await fetch_alerts(app.state.pg_pool, limit)


@app.get("/anomaly-scores")
async def anomaly_scores():
    raw = await app.state.redis.hgetall(ANOMALY_SCORES_KEY)
    return {int(k): float(v) for k, v in raw.items()}


@app.websocket("/ws/live")
async def ws_live(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            raw = await app.state.redis.hgetall(ANOMALY_SCORES_KEY)
            scores = {int(k): float(v) for k, v in raw.items()}
            node_ids = list(scores.keys())
            values_list = await asyncio.gather(
                *(app.state.rolling_store.latest_metric_values(node_id) for node_id in node_ids)
            )
            latest = {
                node_id: {
                    "cpu": values["cpu"],
                    "memory": values["memory"],
                    "latency_ms": values["latency_ms"],
                    "error_rate": values["error_rate"],
                    "ts": values["ts"],
                }
                for node_id, values in zip(node_ids, values_list)
                if values is not None
            }
            await websocket.send_json({"scores": scores, "latest": latest})
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass
