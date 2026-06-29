"""Offline training script for the Phase 2 anomaly detector.

Same synthetic normal/anomaly generators as train_isolation_forest.py, but
trains a sequence-to-sequence LSTM autoencoder on raw (scaled) metric
sequences instead of hand-engineered window statistics. Anomaly score is
the normalized reconstruction error. Swapping MODEL_TYPE=lstm in the
backend picks this up with zero pipeline changes (see ml/inference.py).
"""
import argparse
import asyncio
import pathlib

import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset

from app.db import create_pool, fetch_metrics_by_node
from app.ml.lstm_autoencoder import SEQ_LEN, LSTMAutoencoder, to_sequence
from app.ml.train_isolation_forest import gen_anomaly_reading, gen_normal_reading

INTERVAL_SECONDS = 0.5
STRIDE = 5
EPOCHS = 15
BATCH_SIZE = 64
LR = 1e-3
THRESHOLD = 0.6

ARTIFACT_PATH = pathlib.Path(__file__).parent / "artifacts" / "lstm_autoencoder.pt"


def build_sequences(num_nodes: int, duration_seconds: int, anomaly: bool) -> np.ndarray:
    gen = gen_anomaly_reading if anomaly else gen_normal_reading
    readings_per_node = int(duration_seconds / INTERVAL_SECONDS)
    sequences = []
    for _ in range(num_nodes):
        series = [gen() for _ in range(readings_per_node)]
        for start in range(0, len(series) - SEQ_LEN, STRIDE):
            sequences.append(to_sequence(series[start : start + SEQ_LEN]))
    return np.array(sequences)


def normalize(errors: np.ndarray, error_min: float, error_max: float) -> np.ndarray:
    norm = (errors - error_min) / (error_max - error_min)
    return np.clip(norm, 0.0, 1.0)


def build_sequences_from_rows(rows_by_node: dict, stride: int = STRIDE) -> np.ndarray:
    sequences = []
    for rows in rows_by_node.values():
        for start in range(0, len(rows) - SEQ_LEN, stride):
            sequences.append(to_sequence(rows[start : start + SEQ_LEN]))
    return np.array(sequences)


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
    return build_sequences_from_rows(rows_by_node)


def main(source: str = "synthetic") -> None:
    if source == "db":
        print("Building training sequences from real historical data in Postgres...")
        X_train = build_dataset_from_db()
    else:
        print("Generating synthetic normal training sequences (20 minutes x 50 nodes)...")
        X_train = build_sequences(num_nodes=50, duration_seconds=20 * 60, anomaly=False)
    print(f"Training sequences: {X_train.shape}")

    flat = X_train.reshape(-1, X_train.shape[-1])
    scaler_mean = flat.mean(axis=0)
    scaler_std = flat.std(axis=0) + 1e-6
    X_train_scaled = (X_train - scaler_mean) / scaler_std

    tensor_x = torch.from_numpy(X_train_scaled.astype(np.float32))
    loader = DataLoader(TensorDataset(tensor_x), batch_size=BATCH_SIZE, shuffle=True)

    model = LSTMAutoencoder()
    optimizer = torch.optim.Adam(model.parameters(), lr=LR)
    loss_fn = torch.nn.MSELoss()

    print(f"Training for {EPOCHS} epochs...")
    model.train()
    for epoch in range(EPOCHS):
        total_loss = 0.0
        for (batch,) in loader:
            optimizer.zero_grad()
            reconstruction = model(batch)
            loss = loss_fn(reconstruction, batch)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * batch.size(0)
        print(f"  epoch {epoch + 1}/{EPOCHS} - mse {total_loss / len(tensor_x):.5f}")

    model.eval()
    with torch.no_grad():
        train_recon = model(tensor_x)
        train_errors = torch.mean((train_recon - tensor_x) ** 2, dim=(1, 2)).numpy()
    error_min, error_max = float(train_errors.min()), float(train_errors.max())

    print("Generating synthetic anomaly validation sequences (5 minutes x 10 nodes)...")
    X_anomaly = build_sequences(num_nodes=10, duration_seconds=5 * 60, anomaly=True)
    X_anomaly_scaled = (X_anomaly - scaler_mean) / scaler_std
    tensor_anomaly = torch.from_numpy(X_anomaly_scaled.astype(np.float32))
    with torch.no_grad():
        anomaly_recon = model(tensor_anomaly)
        anomaly_errors = torch.mean((anomaly_recon - tensor_anomaly) ** 2, dim=(1, 2)).numpy()

    train_normalized = normalize(train_errors, error_min, error_max)
    anomaly_normalized = normalize(anomaly_errors, error_min, error_max)
    false_positive_rate = float((train_normalized > THRESHOLD).mean())
    detection_rate = float((anomaly_normalized > THRESHOLD).mean())
    print(f"Normal windows flagged above threshold {THRESHOLD}: {false_positive_rate:.2%} (false positive rate)")
    print(f"Anomaly windows flagged above threshold {THRESHOLD}: {detection_rate:.2%} (detection rate)")

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    torch.save(
        {
            "state_dict": model.state_dict(),
            "scaler_mean": scaler_mean.tolist(),
            "scaler_std": scaler_std.tolist(),
            "error_min": error_min,
            "error_max": error_max,
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
