import { useEffect, useRef, useState } from "react";
import AlertFeed from "./components/AlertFeed";
import FleetGrid from "./components/FleetGrid";
import MetricChart from "./components/MetricChart";
import { connectLiveSocket, fetchAlerts, fetchMetricsHistory, fetchNodes } from "./api";

const METRICS = [
  { key: "cpu", label: "CPU %", color: "#4f9bff", unit: "%" },
  { key: "memory", label: "Memory %", color: "#7c5cff", unit: "%" },
  { key: "latency_ms", label: "Latency", color: "#ffb84f", unit: "ms" },
  { key: "error_rate", label: "Error Rate", color: "#ff5c7c", unit: "" },
];

const HISTORY_LIMIT = 120;

export default function App() {
  const [nodeIds, setNodeIds] = useState([]);
  const [scores, setScores] = useState({});
  const [selectedNode, setSelectedNode] = useState(null);
  const [history, setHistory] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const selectedNodeRef = useRef(null);

  useEffect(() => {
    selectedNodeRef.current = selectedNode;
  }, [selectedNode]);

  useEffect(() => {
    const load = () =>
      fetchNodes().then((ids) => {
        setNodeIds(ids);
        setSelectedNode((current) => (current === null && ids.length ? ids[0] : current));
      });
    load();
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const refresh = () => fetchAlerts(50).then(setAlerts);
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (selectedNode === null) return;
    fetchMetricsHistory(selectedNode, HISTORY_LIMIT).then((rows) => {
      setHistory(
        rows.map((r) => ({
          ts: Date.parse(r.recorded_at) / 1000,
          cpu: r.cpu,
          memory: r.memory,
          latency_ms: r.latency_ms,
          error_rate: r.error_rate,
        }))
      );
    });
  }, [selectedNode]);

  useEffect(() => {
    const ws = connectLiveSocket((payload) => {
      setScores(payload.scores);
      const node = selectedNodeRef.current;
      if (node !== null && payload.latest[node]) {
        const point = payload.latest[node];
        setHistory((prev) => {
          const next = [...prev, point];
          return next.length > HISTORY_LIMIT ? next.slice(next.length - HISTORY_LIMIT) : next;
        });
      }
    });
    return () => ws.close();
  }, []);

  return (
    <div className="app">
      <header className="app__header">
        <h1>PulseAI</h1>
        <p>Real-time fleet anomaly detection</p>
      </header>
      <main className="app__main">
        <section className="app__fleet">
          <h3>Fleet ({nodeIds.length} nodes)</h3>
          <FleetGrid
            nodeIds={nodeIds}
            scores={scores}
            selectedNode={selectedNode}
            onSelectNode={setSelectedNode}
          />
        </section>
        <section className="app__detail">
          <h3>Node {selectedNode ?? "--"} detail</h3>
          <div className="metric-grid">
            {METRICS.map((m) => (
              <MetricChart
                key={m.key}
                title={m.label}
                data={history}
                dataKey={m.key}
                color={m.color}
                unit={m.unit}
              />
            ))}
          </div>
        </section>
        <section className="app__alerts">
          <AlertFeed alerts={alerts} />
        </section>
      </main>
    </div>
  );
}
