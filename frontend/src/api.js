const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const WS_BASE = API_BASE.replace(/^http/, "ws");

async function getJson(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json();
}

export function fetchNodes() {
  return getJson("/nodes");
}

export function fetchAlerts(limit = 100) {
  return getJson(`/alerts?limit=${limit}`);
}

export async function fetchMetricsHistory(nodeId, limit = 120) {
  const rows = await getJson(`/metrics/latest?node_id=${nodeId}&limit=${limit}`);
  return rows.reverse();
}

// Reconnects with exponential backoff (1s -> 10s) so a backend restart doesn't
// leave the dashboard silently frozen. onStatus gets "connecting" | "live" | "reconnecting".
export function connectLiveSocket(onMessage, onStatus = () => {}) {
  let ws;
  let retryMs = 1000;
  let retryTimer;
  let closed = false;

  const open = () => {
    ws = new WebSocket(`${WS_BASE}/ws/live`);
    ws.onopen = () => {
      retryMs = 1000;
      onStatus("live");
    };
    ws.onmessage = (event) => onMessage(JSON.parse(event.data));
    ws.onclose = () => {
      if (closed) return;
      onStatus("reconnecting");
      retryTimer = setTimeout(open, retryMs);
      retryMs = Math.min(retryMs * 2, 10000);
    };
  };

  onStatus("connecting");
  open();
  return {
    close() {
      closed = true;
      clearTimeout(retryTimer);
      ws.close();
    },
  };
}
