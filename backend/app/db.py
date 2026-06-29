import os

import asyncpg

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://pulse:pulse@localhost:5432/pulseai")

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS raw_metrics (
    id BIGSERIAL PRIMARY KEY,
    node_id INTEGER NOT NULL,
    cpu DOUBLE PRECISION NOT NULL,
    memory DOUBLE PRECISION NOT NULL,
    latency_ms DOUBLE PRECISION NOT NULL,
    error_rate DOUBLE PRECISION NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_raw_metrics_node_time ON raw_metrics (node_id, recorded_at DESC);

CREATE TABLE IF NOT EXISTS alerts (
    id BIGSERIAL PRIMARY KEY,
    node_id INTEGER NOT NULL,
    metric TEXT NOT NULL,
    score DOUBLE PRECISION NOT NULL,
    severity TEXT NOT NULL,
    message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


async def create_pool() -> asyncpg.Pool:
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    async with pool.acquire() as conn:
        await conn.execute(CREATE_TABLES_SQL)
    return pool


async def insert_alert(
    pool: asyncpg.Pool, node_id: int, metric: str, score: float, severity: str, message: str
) -> int:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO alerts (node_id, metric, score, severity, message) "
            "VALUES ($1, $2, $3, $4, $5) RETURNING id",
            node_id,
            metric,
            score,
            severity,
            message,
        )
    return row["id"]


async def fetch_alerts(pool: asyncpg.Pool, limit: int = 100) -> list[dict]:
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT id, node_id, metric, score, severity, message, created_at "
            "FROM alerts ORDER BY created_at DESC LIMIT $1",
            limit,
        )
    return [dict(r) for r in rows]


async def fetch_metrics_by_node(pool: asyncpg.Pool) -> dict:
    """All raw_metrics rows, grouped by node and ordered chronologically.

    Used by the offline training scripts' --source db path so models can be
    retrained on whatever telemetry has actually flowed through the pipeline
    instead of synthetic data.
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT node_id, cpu, memory, latency_ms, error_rate, recorded_at "
            "FROM raw_metrics ORDER BY node_id, recorded_at"
        )
    by_node: dict = {}
    for r in rows:
        by_node.setdefault(r["node_id"], []).append(
            {
                "cpu": r["cpu"],
                "memory": r["memory"],
                "latency_ms": r["latency_ms"],
                "error_rate": r["error_rate"],
                "ts": r["recorded_at"].timestamp(),
            }
        )
    return by_node


async def insert_metrics_batch(pool: asyncpg.Pool, batch: list[dict]) -> None:
    records = [
        (m["node_id"], m["cpu"], m["memory"], m["latency_ms"], m["error_rate"], m["recorded_at"])
        for m in batch
    ]
    async with pool.acquire() as conn:
        await conn.copy_records_to_table(
            "raw_metrics",
            records=records,
            columns=["node_id", "cpu", "memory", "latency_ms", "error_rate", "recorded_at"],
        )
