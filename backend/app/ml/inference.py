import pathlib
from abc import ABC, abstractmethod

import joblib
import numpy as np

from ..features import compute_features

ARTIFACTS_DIR = pathlib.Path(__file__).parent / "artifacts"


class AnomalyScorer(ABC):
    threshold: float = 0.6

    @abstractmethod
    def score(self, window: list) -> float:
        """Return an anomaly probability in [0, 1] for a window of metric dicts."""


class IsolationForestScorer(AnomalyScorer):
    def __init__(self, artifact_path: pathlib.Path):
        artifact = joblib.load(artifact_path)
        self.model = artifact["model"]
        self.score_min = artifact["score_min"]
        self.score_max = artifact["score_max"]
        self.threshold = artifact["threshold"]

    def score(self, window: list) -> float:
        features = compute_features(window)
        raw = self.model.score_samples(features.reshape(1, -1))[0]
        normalized = (self.score_max - raw) / (self.score_max - self.score_min)
        return float(np.clip(normalized, 0.0, 1.0))


def load_scorer(model_type: str = "isolation_forest") -> AnomalyScorer:
    if model_type == "isolation_forest":
        return IsolationForestScorer(ARTIFACTS_DIR / "isolation_forest.joblib")
    if model_type == "lstm":
        from .lstm_autoencoder import LSTMScorer

        return LSTMScorer(ARTIFACTS_DIR / "lstm_autoencoder.pt")
    raise ValueError(f"Unknown model_type: {model_type}")
