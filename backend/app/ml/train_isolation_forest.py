"""Offline training script for the Phase 1 anomaly detector.

Generates synthetic "normal" telemetry matching the simulator's distributions,
trains an IsolationForest on rolling-window features, then validates against
synthetic injected anomalies (CPU/latency/error-rate spikes) before saving the
artifact that app/ml/inference.py loads at runtime.
"""
import argparse
import asyncio
import pathlib

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest

from app.db import create_pool, fetch_metrics_by_node
from app.features import FEATURE_NAMES, build_feature_dataset_from_rows, compute_features

RNG = np.random.default_rng(42)
INTERVAL_SECONDS = 0.5
WINDOW_READINGS = 120  # 60s at 0.5s interval, matches RollingWindowStore
STEP_READINGS = 4  # slide the window every 2s of simulated time
THRESHOLD = 0.6

ARTIFACT_PATH = pathlib.Path(__file__).parent / "artifacts" / "isolation_forest.joblib"


def gen_normal_reading() -> dict:
    return {
        "cpu": max(0.0, RNG.normal(45, 10)),
        "memory": max(0.0, RNG.normal(60, 8)),
        "latency_ms": max(0.0, RNG.normal(120, 20)),
        "error_rate": max(0.0, RNG.normal(0.02, 0.005)),
    }


def gen_anomaly_reading() -> dict:
    return {
        "cpu": max(0.0, RNG.normal(92, 4)),
        "memory": max(0.0, RNG.normal(88, 5)),
        "latency_ms": max(0.0, RNG.normal(750, 80)),
        "error_rate": max(0.0, RNG.normal(0.25, 0.05)),
    }


def build_dataset(num_nodes: int, duration_seconds: int, anomaly: bool) -> np.ndarray:
    gen = gen_anomaly_reading if anomaly else gen_normal_reading
    readings_per_node = int(duration_seconds / INTERVAL_SECONDS)
    rows = []
    for _ in range(num_nodes):
        series = [gen() for _ in range(readings_per_node)]
        for start in range(0, len(series) - WINDOW_READINGS, STEP_READINGS):
            rows.append(compute_features(series[start : start + WINDOW_READINGS]))
    return np.array(rows)


def normalize(raw_scores: np.ndarray, score_min: float, score_max: float) -> np.ndarray:
    norm = (score_max - raw_scores) / (score_max - score_min)
    return np.clip(norm, 0.0, 1.0)


def build_dataset_from_db() -> np.ndarray:
    async def _load():
        pool = await create_pool()
        try:
            return await fetch_metrics_by_node(pool)
        finally:
            await pool.close()

    rows_by_node = asyncio.run(_load())
    if not rows_by_node:
        raise SystemExit(
            "No data found in raw_metrics. Let the pipeline run for a few minutes first, "
            "or use --source synthetic."
        )
    total_rows = sum(len(rows) for rows in rows_by_node.values())
    print(f"Loaded {total_rows} rows across {len(rows_by_node)} nodes from Postgres.")
    return build_feature_dataset_from_rows(rows_by_node)


def main(source: str = "synthetic") -> None:
    if source == "db":
        print("Building training features from real historical data in Postgres...")
        X_train = build_dataset_from_db()
    else:
        print("Generating synthetic normal training data (30 minutes x 50 nodes)...")
        X_train = build_dataset(num_nodes=50, duration_seconds=30 * 60, anomaly=False)
    print(f"Training feature matrix: {X_train.shape}")

    model = IsolationForest(n_estimators=200, contamination=0.02, random_state=42)
    model.fit(X_train)

    train_scores = model.score_samples(X_train)
    score_min, score_max = float(train_scores.min()), float(train_scores.max())

    print("Generating synthetic anomaly validation data (5 minutes x 10 nodes)...")
    X_anomaly = build_dataset(num_nodes=10, duration_seconds=5 * 60, anomaly=True)
    anomaly_scores = model.score_samples(X_anomaly)

    train_normalized = normalize(train_scores, score_min, score_max)
    anomaly_normalized = normalize(anomaly_scores, score_min, score_max)

    false_positive_rate = float((train_normalized > THRESHOLD).mean())
    detection_rate = float((anomaly_normalized > THRESHOLD).mean())
    print(f"Normal windows flagged above threshold {THRESHOLD}: {false_positive_rate:.2%} (false positive rate)")
    print(f"Anomaly windows flagged above threshold {THRESHOLD}: {detection_rate:.2%} (detection rate)")

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "score_min": score_min,
            "score_max": score_max,
            "feature_names": FEATURE_NAMES,
            "threshold": THRESHOLD,
        },
        ARTIFACT_PATH,
    )
    print(f"Saved model artifact to {ARTIFACT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        choices=["synthetic", "db"],
        default="synthetic",
        help="synthetic: generate normal telemetry inline. db: train on real raw_metrics history.",
    )
    args = parser.parse_args()
    main(source=args.source)
