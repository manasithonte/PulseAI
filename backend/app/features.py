from collections import defaultdict, deque
from typing import Optional

import numpy as np

WINDOW_SECONDS = 60
MIN_SAMPLES = 5
METRIC_NAMES = ["cpu", "memory", "latency_ms", "error_rate"]
STAT_NAMES = ["mean", "std", "min", "max"]
FEATURE_NAMES = [f"{m}_{s}" for m in METRIC_NAMES for s in STAT_NAMES]


def compute_features(window: list) -> np.ndarray:
    """Mean/std/min/max per metric over a window of metric dicts.

    Shared by the live RollingWindowStore and the offline training script so
    inference and training always see identically-shaped feature vectors.
    """
    feats = []
    for metric in METRIC_NAMES:
        values = np.array([r[metric] for r in window], dtype=np.float64)
        feats.extend([values.mean(), values.std(), values.min(), values.max()])
    return np.array(feats, dtype=np.float64)


class RollingWindowStore:
    """Keeps an in-memory rolling window of recent metrics per node so feature
    extraction doesn't need a DB round trip on the hot inference path."""

    def __init__(self, window_seconds: int = WINDOW_SECONDS):
        self.window_seconds = window_seconds
        self._buffers: dict[int, deque] = defaultdict(deque)

    def add(self, node_id: int, metrics: dict, ts: float) -> None:
        buf = self._buffers[node_id]
        buf.append((ts, metrics))
        cutoff = ts - self.window_seconds
        while buf and buf[0][0] < cutoff:
            buf.popleft()

    def window(self, node_id: int) -> Optional[list]:
        buf = self._buffers.get(node_id)
        if not buf or len(buf) < MIN_SAMPLES:
            return None
        return [m for _, m in buf]

    def features(self, node_id: int) -> Optional[np.ndarray]:
        window = self.window(node_id)
        if window is None:
            return None
        return compute_features(window)

    def latest_metric_values(self, node_id: int) -> Optional[dict]:
        buf = self._buffers.get(node_id)
        if not buf:
            return None
        return buf[-1][1]


def build_feature_dataset_from_rows(rows_by_node: dict, stride: int = 4) -> np.ndarray:
    """Replay historical (node_id -> chronological rows) through a rolling
    window exactly like the live pipeline does, sampling a feature vector
    every `stride` rows. Lets training scripts learn from whatever telemetry
    actually flowed through Postgres instead of only synthetic generators,
    while guaranteeing identical feature shape/semantics to live inference.
    """
    store = RollingWindowStore()
    out = []
    for node_id, rows in rows_by_node.items():
        for i, row in enumerate(rows):
            store.add(node_id, row, row["ts"])
            if i % stride == 0:
                window = store.window(node_id)
                if window is not None:
                    out.append(compute_features(window))
    return np.array(out)
