# PulseAI

Real-time fleet anomaly detection: 50 simulated nodes stream CPU/memory/latency/error-rate
metrics through Redis Streams into a FastAPI consumer that scores every node against a
rolling 60-second window with a swappable ML model (Isolation Forest or LSTM Autoencoder),
persists everything to Postgres, and pushes live state to a React dashboard over WebSockets.
Anomalies above threshold raise Slack/email alerts.

## Architecture

```
 ┌──────────────┐     XADD      ┌───────────┐   XREADGROUP    ┌──────────────────┐
 │  simulator   │ ───────────▶  │  Redis    │ ──────────────▶ │  backend (1..N)    │
 │ 50 async     │   metrics_    │  Streams  │   (consumer     │  replicas, FastAPI │
 │ coroutines   │   stream      │           │    group)       │                    │
 └──────────────┘               └───────────┘                 │  ┌──────────────┐  │
                                                                │  │ AnomalyScorer│  │
                                       ┌─────────────────┐     │  │ (IF or LSTM) │  │
                                       │   anomaly_scores,│◀────┤  └──────┬───────┘  │
                                       │   rolling:{node},│     │         ▼          │
                                       │   alert_cooldown │     │  raw_metrics /     │
                                       │   (Redis, shared │     │  alerts (Postgres) │
                                       │   across replicas)│     └─────────┬──────────┘
                                       └─────────┬─────────┘               │
                                                 │                         │
                                          GET /ws/live              Slack / SendGrid
                                                 │
                                                 ▼
                                       ┌───────────────────┐
                                       │  React dashboard   │
                                       │  fleet grid, charts,│
                                       │  alert feed         │
                                       └───────────────────┘
```

## Tech stack

| Layer | Tech |
|---|---|
| Simulation | Python `asyncio`, 50 concurrent producers |
| Streaming | Redis Streams (consumer group, `XACK`-based at-least-once delivery) |
| Backend | FastAPI + WebSockets |
| ML (Phase 1) | Isolation Forest (`scikit-learn`) on rolling-window features |
| ML (Phase 2) | LSTM Autoencoder (PyTorch) on raw sequences, swappable via `MODEL_TYPE` |
| Storage | PostgreSQL (raw metrics, alert history) |
| Cache / live state | Redis (anomaly scores, stream backbone) |
| Frontend | React (Vite) + Recharts |
| Alerts | Slack incoming webhook + SendGrid email |
| Deployment | Docker Compose |

## Running it

Requires Docker.

```bash
docker compose up -d --build
```

This starts Redis, Postgres, the 50-node simulator, the FastAPI backend, and the frontend
(nginx-served React build) on:

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000 (docs at `/docs`)
- WebSocket: `ws://localhost:8000/ws/live`

The repo ships with pre-trained model artifacts (`backend/app/ml/artifacts/*.joblib`, `*.pt`),
so detection works immediately. To retrain either model on freshly generated synthetic data:

```bash
docker compose run --rm backend python -m app.ml.train_isolation_forest
docker compose run --rm backend python -m app.ml.train_lstm
```

Both scripts train on synthetic "normal" telemetry, validate against synthetic injected
anomalies (CPU/latency/error-rate spikes), print false-positive/detection rates, and save the
artifact that `app/ml/inference.py` loads at startup. Artifacts are bind-mounted into the
backend container, so a retrain takes effect on the next `docker compose up -d backend`
without rebuilding the image.

#### Training on real data instead of synthetic

```bash
docker compose run --rm backend python -m app.ml.train_isolation_forest --source db
docker compose run --rm backend python -m app.ml.train_lstm --source db
```

`--source db` pulls whatever has actually accumulated in the `raw_metrics` table and replays
it through the same windowing logic the live pipeline uses (`features.build_feature_dataset_from_rows`),
instead of generating synthetic arrays inline — this is the path a real deployment would use.
One caveat found while testing it: if the historical data already contains real anomaly
bursts (which it will, since the simulator injects some), the LSTM's error-normalization range
gets calibrated against those too, and a held-out *synthetic* anomaly can land well under
threshold even though the model scores it ~13x higher than normal — the validation step still
needs genuinely-held-out real anomalies to mean anything once training data isn't clean. The
shipped artifacts in this repo are trained on synthetic data so the documented benchmark
numbers below stay reproducible; `--source db` is there to retrain against your own field data
once you have some.

### Switching models

```bash
MODEL_TYPE=lstm docker compose up -d backend   # default is isolation_forest
```

Both models implement the same `AnomalyScorer.score(window) -> float[0,1]` interface
(`backend/app/ml/inference.py`), so swapping models never touches the consumer pipeline.

### Alerts (optional)

Copy `.env.example` to `.env` and fill in a Slack webhook URL and/or SendGrid credentials.
Both integrations no-op safely (with a log line) when left blank — alerts still write to the
Postgres `alerts` table and the live feed either way.

### Running multiple backend replicas

The rolling window, anomaly scores, and alert cooldown all live in Redis
(`backend/app/redis_store.py`), not in process memory, so multiple backend replicas consuming
the same Redis Streams consumer group share consistent state instead of each seeing a
different partial view.

`docker-compose.yml` publishes a single fixed host port (`8000:8000`), so `--scale backend=2`
will fail outright on a port conflict as-is — that's intentional for the default single-instance
case, not a bug. To actually test scaling, widen the port mapping to a range first:

```bash
sed -i '' 's/"8000:8000"/"8000-8001:8000"/' docker-compose.yml   # macOS sed; drop '' on Linux
docker compose up -d --scale backend=2 backend
# ...verify via `docker compose logs backend` and `redis-cli XINFO CONSUMERS ...`...
docker compose up -d --scale backend=1 backend
git checkout docker-compose.yml   # or just revert the port line manually
docker compose rm -sf backend && docker compose up -d backend  # clean recreate on :8000
```

Each replica gets a unique consumer name (`backend-<hostname>`) so Redis can track pending
entries per replica. If a replica dies or restarts mid-batch, `XAUTOCLAIM` reclaims anything
left pending for >30s on the next loop iteration, so in-flight messages aren't lost. The alert
cooldown uses an atomic `SET NX EX` in Redis, so two replicas independently flagging the same
node won't both fire an alert — verified by running 2 replicas this way and confirming repeat
alerts for the same node landed exactly 30s apart (the cooldown boundary), never closer,
regardless of which replica processed them. A real multi-replica deployment would put a load
balancer in front rather than rely on host port mappings at all — this is just how to exercise
the shared-state logic locally.

## Benchmarks (measured locally)

| Model | False positive rate | Detection rate (synthetic anomalies) |
|---|---|---|
| Isolation Forest | 1.8% | 100% |
| LSTM Autoencoder | 10.8% | 100% |

Inference latency, measured in the live pipeline (49-node batch, Isolation Forest):
**~90ms per batch (~1.9ms/node) with in-process state, ~120-130ms (~2.6ms/node) with the
Redis-backed store** — both well under the 200ms target. The difference is the extra
network round trips per node now that window state lives in Redis instead of memory.

The LSTM's higher false-positive rate is expected: the simulator generates i.i.d. Gaussian
noise per tick, so there's little real temporal structure for an LSTM to exploit over an
Isolation Forest baseline. It's kept in the repo to demonstrate the swappable-model
architecture (Phase 1 → Phase 2 upgrade path), with Isolation Forest as the better-performing
default.

## Demo anomaly rate

The simulator injects rare CPU/memory/latency/error-rate spikes per node
(`ANOMALY_PROBABILITY`, `ANOMALY_DURATION_TICKS` env vars in `simulator/simulate.py`, default
~1-in-1000 chance per 0.5s tick, lasting 5s). Tune these to make the dashboard busier or
quieter.

## Security (not implemented — do this before exposing it to anything but your own machine)

This stack has zero auth and is safe only on a trusted local network. Specifically:

- **CORS is wide open** (`allow_origins=["*"]` in `backend/app/main.py`) and there's no auth
  on the REST endpoints or the `/ws/live` WebSocket — anyone who can reach port 8000 can read
  all metrics/alerts and hold a live connection open.
- **Postgres and Redis use hardcoded credentials** (`pulse`/`pulse`) in `docker-compose.yml`,
  fine for a local-only network namespace, not fine if either port is reachable from outside.
- No TLS anywhere — normally handled by a reverse proxy/ingress in front of the app rather
  than the app itself, but there isn't one here.

If this ever needs to leave your own machine: put a real secret behind `CORS allow_origins`
and a bearer-token check on the REST/WS routes, move the Postgres/Redis passwords into
`.env`-sourced secrets instead of the compose file, and put it behind a TLS-terminating proxy
(nginx, Caddy, or whatever ingress your deployment target provides).
