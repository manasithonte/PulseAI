import pathlib

import numpy as np
import torch
import torch.nn as nn

from ..features import METRIC_NAMES
from .inference import AnomalyScorer

SEQ_LEN = 30
INPUT_SIZE = len(METRIC_NAMES)
HIDDEN_SIZE = 16


class LSTMAutoencoder(nn.Module):
    def __init__(self, input_size: int = INPUT_SIZE, hidden_size: int = HIDDEN_SIZE, seq_len: int = SEQ_LEN):
        super().__init__()
        self.seq_len = seq_len
        self.encoder = nn.LSTM(input_size, hidden_size, batch_first=True)
        self.decoder = nn.LSTM(hidden_size, hidden_size, batch_first=True)
        self.output_layer = nn.Linear(hidden_size, input_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        _, (hidden, _) = self.encoder(x)
        latent = hidden[-1].unsqueeze(1).repeat(1, self.seq_len, 1)
        decoded, _ = self.decoder(latent)
        return self.output_layer(decoded)


def to_sequence(window: list, seq_len: int = SEQ_LEN) -> np.ndarray:
    if len(window) >= seq_len:
        sub = window[-seq_len:]
    else:
        sub = [window[0]] * (seq_len - len(window)) + list(window)
    return np.array([[r[m] for m in METRIC_NAMES] for r in sub], dtype=np.float32)


class LSTMScorer(AnomalyScorer):
    def __init__(self, artifact_path: pathlib.Path):
        artifact = torch.load(artifact_path, map_location="cpu", weights_only=False)
        self.model = LSTMAutoencoder()
        self.model.load_state_dict(artifact["state_dict"])
        self.model.eval()
        self.scaler_mean = np.array(artifact["scaler_mean"], dtype=np.float32)
        self.scaler_std = np.array(artifact["scaler_std"], dtype=np.float32)
        self.error_min = artifact["error_min"]
        self.error_max = artifact["error_max"]
        self.threshold = artifact["threshold"]

    def score(self, window: list) -> float:
        sequence = to_sequence(window)
        scaled = (sequence - self.scaler_mean) / self.scaler_std
        tensor = torch.from_numpy(scaled).unsqueeze(0)
        with torch.no_grad():
            reconstruction = self.model(tensor)
            error = torch.mean((reconstruction - tensor) ** 2).item()
        normalized = (error - self.error_min) / (self.error_max - self.error_min)
        return float(np.clip(normalized, 0.0, 1.0))
