import numpy as np
import pytest

from app.features import (
    FEATURE_NAMES,
    MIN_SAMPLES,
    RollingWindowStore,
    build_feature_dataset_from_rows,
    compute_features,
)


def reading(cpu=1.0, memory=2.0, latency_ms=3.0, error_rate=4.0) -> dict:
    return {"cpu": cpu, "memory": memory, "latency_ms": latency_ms, "error_rate": error_rate}


def test_compute_features_shape_and_order():
    window = [reading(cpu=10.0), reading(cpu=20.0), reading(cpu=30.0)]
    feats = compute_features(window)

    assert feats.shape == (len(FEATURE_NAMES),)
    cpu = dict(zip(FEATURE_NAMES, feats))
    assert cpu["cpu_mean"] == pytest.approx(20.0)
    assert cpu["cpu_std"] == pytest.approx(np.std([10.0, 20.0, 30.0]))
    assert cpu["cpu_min"] == 10.0
    assert cpu["cpu_max"] == 30.0
    # Constant metrics have zero spread.
    assert cpu["memory_std"] == 0.0


def test_window_requires_min_samples():
    store = RollingWindowStore()
    for i in range(MIN_SAMPLES - 1):
        store.add(1, reading(), ts=float(i))
    assert store.window(1) is None
    assert store.features(1) is None

    store.add(1, reading(), ts=float(MIN_SAMPLES))
    assert len(store.window(1)) == MIN_SAMPLES


def test_window_evicts_readings_older_than_window():
    store = RollingWindowStore(window_seconds=10)
    for ts in range(20):
        store.add(1, reading(cpu=float(ts)), ts=float(ts))

    cpus = [r["cpu"] for r in store.window(1)]
    assert cpus == [float(ts) for ts in range(9, 20)]


def test_nodes_are_isolated():
    store = RollingWindowStore()
    for i in range(MIN_SAMPLES):
        store.add(1, reading(cpu=1.0), ts=float(i))
    store.add(2, reading(cpu=99.0), ts=0.0)

    assert store.window(2) is None
    assert store.latest_metric_values(2)["cpu"] == 99.0
    assert store.latest_metric_values(3) is None


def test_build_feature_dataset_from_rows_matches_live_windowing():
    rows = [reading(cpu=float(i)) | {"ts": i * 0.5} for i in range(40)]
    dataset = build_feature_dataset_from_rows({1: rows}, stride=4)

    # Rows 0..39 sampled every 4th; the first MIN_SAMPLES-1 rows can't form a window.
    sampled = [i for i in range(40) if i % 4 == 0 and i + 1 >= MIN_SAMPLES]
    assert dataset.shape == (len(sampled), len(FEATURE_NAMES))
    expected_last = compute_features(rows[: sampled[-1] + 1])
    np.testing.assert_allclose(dataset[-1], expected_last)
