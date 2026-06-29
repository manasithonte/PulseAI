const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";
const WS_BASE = API_BASE.replace(/^http/, "ws");

export async function fetchNodes() {
  const res = await fetch(`${API_BASE}/nodes`);
  return res.json();
}

export async function fetchAlerts(limit = 100) {
  const res = await fetch(`${API_BASE}/alerts?limit=${limit}`);
  return res.json();
}

export async function fetchMetricsHistory(nodeId, limit = 120) {
  const res = await fetch(`${API_BASE}/metrics/latest?node_id=${nodeId}&limit=${limit}`);
  const rows = await res.json();
  return rows.reverse();
}

export function connectLiveSocket(onMessage) {
  const ws = new WebSocket(`${WS_BASE}/ws/live`);
  ws.onmessage = (event) => onMessage(JSON.parse(event.data));
  return ws;
}
