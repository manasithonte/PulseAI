"""Smoke tests against the shipped model artifacts, so a retrain that breaks
detection (or an artifact that no longer loads) fails CI."""
import pytest

from app.ml.inference import load_scorer

from .conftest import anomaly_reading, normal_reading

# Ceilings well above the README benchmarks (1.8% / 10.8%) so only a real
# regression trips them; a single healthy window can legitimately score high.
MAX_FALSE_POSITIVE_RATE = {"isolation_forest": 0.05, "lstm": 0.25}


def _scorer(model_type: str):
    if model_type == "lstm":
        pytest.importorskip("torch")
    return load_scorer(model_type)


@pytest.mark.parametrize("model_type", ["isolation_forest", "lstm"])
def test_scores_are_probabilities(model_type, normal_window, anomaly_window):
    scorer = _scorer(model_type)
    for window in (normal_window, anomaly_window, normal_window[:5]):
        assert 0.0 <= scorer.score(window) <= 1.0


@pytest.mark.parametrize("model_type", ["isolation_forest", "lstm"])
def test_false_positive_rate_on_healthy_windows(model_type, rng):
    scorer = _scorer(model_type)
    windows = [[normal_reading(rng) for _ in range(120)] for _ in range(200)]
    flagged = sum(scorer.score(w) > scorer.threshold for w in windows)
    assert flagged / len(windows) <= MAX_FALSE_POSITIVE_RATE[model_type]


@pytest.mark.parametrize("model_type", ["isolation_forest", "lstm"])
def test_full_anomaly_window_is_flagged(model_type, anomaly_window):
    scorer = _scorer(model_type)
    assert scorer.score(anomaly_window) > scorer.threshold


@pytest.mark.parametrize("model_type", ["isolation_forest", "lstm"])
def test_short_burst_is_flagged(model_type, rng, normal_window):
    """The simulator's default anomaly lasts 10 ticks (5s) inside a 60s window."""
    scorer = _scorer(model_type)
    window = normal_window[:-10] + [anomaly_reading(rng) for _ in range(10)]
    assert scorer.score(window) > scorer.threshold


def test_unknown_model_type_raises():
    with pytest.raises(ValueError):
        load_scorer("not_a_model")
