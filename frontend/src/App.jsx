import { useEffect, useMemo, useRef, useState } from "react";
import AboutPanel from "./components/AboutPanel";
import AlertFeed from "./components/AlertFeed";
import FleetGrid from "./components/FleetGrid";
import NodeDetail from "./components/NodeDetail";
import SummaryBar from "./components/SummaryBar";
import { connectLiveSocket, fetchAlerts, fetchMetricsHistory, fetchNodes } from "./api";
import { statusFor } from "./status";

const HISTORY_LIMIT = 120;
const SCORE_HISTORY_LIMIT = 120; // ~2 minutes at one WebSocket push per second
const ALERT_LIMIT = 50;

const CONNECTION_LABEL = { connecting: "Connecting…", live: "Live", reconnecting: "Reconnecting…" };
const ABOUT_DISMISSED_KEY = "pulseai.aboutDismissed";

function readAboutDismissed() {
  try {
    return localStorage.getItem(ABOUT_DISMISSED_KEY) === "1";
  } catch {
    return false;
  }
}

function writeAboutDismissed(dismissed) {
  try {
    if (dismissed) localStorage.setItem(ABOUT_DISMISSED_KEY, "1");
    else localStorage.removeItem(ABOUT_DISMISSED_KEY);
  } catch {
    // Storage can be unavailable (private mode); the panel just reappears next visit.
  }
}

export default function App() {
  const [nodeIds, setNodeIds] = useState([]);
  const [scores, setScores] = useState({});
  const [scoreHistory, setScoreHistory] = useState({});
  const [selectedNode, setSelectedNode] = useState(null);
  const [history, setHistory] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [connection, setConnection] = useState("connecting");
  const [fleetFilter, setFleetFilter] = useState("all");
  const [showAbout, setShowAbout] = useState(() => !readAboutDismissed());
  const selectedNodeRef = useRef(null);

  const toggleAbout = (show) => {
    setShowAbout(show);
    writeAboutDismissed(!show);
  };

  useEffect(() => {
    selectedNodeRef.current = selectedNode;
  }, [selectedNode]);

  useEffect(() => {
    const load = () =>
      fetchNodes()
        .then((ids) => {
          setNodeIds(ids);
          setSelectedNode((current) => (current === null && ids.length ? ids[0] : current));
        })
        .catch(() => {});
    load();
    const interval = setInterval(load, 30000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const refresh = () => fetchAlerts(ALERT_LIMIT).then(setAlerts).catch(() => {});
    refresh();
    const interval = setInterval(refresh, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (selectedNode === null) return;
    let cancelled = false;
    setHistory([]);
    fetchMetricsHistory(selectedNode, HISTORY_LIMIT)
      .then((rows) => {
        if (cancelled) return;
        setHistory(
          rows.map((r) => ({
            ts: Date.parse(r.recorded_at) / 1000,
            cpu: r.cpu,
            memory: r.memory,
            latency_ms: r.latency_ms,
            error_rate: r.error_rate,
          }))
        );
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [selectedNode]);

  useEffect(() => {
    const socket = connectLiveSocket((payload) => {
      setScores(payload.scores);

      const now = Date.now() / 1000;
      setScoreHistory((prev) => {
        const next = { ...prev };
        for (const [nodeId, score] of Object.entries(payload.scores)) {
          const series = [...(prev[nodeId] ?? []), { ts: now, score }];
          next[nodeId] = series.length > SCORE_HISTORY_LIMIT ? series.slice(-SCORE_HISTORY_LIMIT) : series;
        }
        return next;
      });

      const node = selectedNodeRef.current;
      if (node !== null && payload.latest[node]) {
        const point = payload.latest[node];
        setHistory((prev) => {
          // The socket pushes every second but nodes report every 0.5s, so the
          // same reading can arrive twice; skip anything not newer than the tail.
          if (prev.length && point.ts <= prev[prev.length - 1].ts) return prev;
          const next = [...prev, point];
          return next.length > HISTORY_LIMIT ? next.slice(next.length - HISTORY_LIMIT) : next;
        });
      }
    }, setConnection);
    return () => socket.close();
  }, []);

  const counts = useMemo(() => {
    const c = { healthy: 0, warning: 0, critical: 0 };
    for (const id of nodeIds) {
      const status = statusFor(scores[id]);
      if (status in c) c[status] += 1;
    }
    return c;
  }, [nodeIds, scores]);

  return (
    <div className="app">
      <header className="app__header">
        <div className="brand">
          <svg className="brand__mark" viewBox="0 0 24 24" aria-hidden="true">
            <path d="M2 12h4l2.5-6 4 12 3-9 2 3H22" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <div>
            <h1>PulseAI</h1>
            <p>Spots misbehaving servers in real time with machine learning</p>
          </div>
        </div>
        <div className="app__header-tools">
          <button className="about-toggle" onClick={() => toggleAbout(!showAbout)} aria-expanded={showAbout}>
            {showAbout ? "Hide about" : "About"}
          </button>
          <div className={`connection connection--${connection}`} role="status">
            <span className="connection__dot" />
            {CONNECTION_LABEL[connection]}
          </div>
        </div>
      </header>

      {showAbout && (
        <div className="app__about">
          <AboutPanel nodeCount={nodeIds.length} onClose={() => toggleAbout(false)} />
        </div>
      )}

      <main className="app__main">
        <section className="app__summary">
          <SummaryBar counts={counts} total={nodeIds.length} alerts={alerts} alertLimit={ALERT_LIMIT} />
        </section>
        <section className="app__fleet">
          <FleetGrid
            nodeIds={nodeIds}
            scores={scores}
            selectedNode={selectedNode}
            onSelectNode={setSelectedNode}
            filter={fleetFilter}
            onFilterChange={setFleetFilter}
          />
        </section>
        <section className="app__detail">
          <NodeDetail
            nodeId={selectedNode}
            score={scores[selectedNode]}
            scoreHistory={scoreHistory[selectedNode] ?? []}
            history={history}
          />
        </section>
        <aside className="app__alerts">
          <AlertFeed alerts={alerts} selectedNode={selectedNode} onSelectNode={setSelectedNode} />
        </aside>
      </main>
    </div>
  );
}
