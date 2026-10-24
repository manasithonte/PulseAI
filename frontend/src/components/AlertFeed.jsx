import { useState } from "react";
import { METRIC_LABEL, STATUS_LABEL, timeAgo } from "../status";
import StatusIcon from "./StatusIcon";

const FILTERS = ["all", "critical", "warning"];

export default function AlertFeed({ alerts, selectedNode, onSelectNode }) {
  const [filter, setFilter] = useState("all");
  const visible = filter === "all" ? alerts : alerts.filter((a) => a.severity === filter);
  const now = Date.now();

  return (
    <div className="panel alert-feed">
      <div className="panel__header">
        <h2>
          Alerts <span className="panel__count">{alerts.length} recent</span>
        </h2>
        <div className="segmented" role="group" aria-label="Filter alerts by severity">
          {FILTERS.map((f) => (
            <button key={f} className={filter === f ? "is-active" : ""} onClick={() => setFilter(f)}>
              {f === "all" ? "All" : STATUS_LABEL[f]}
            </button>
          ))}
        </div>
      </div>

      <p className="panel__description">Raised when a node's score crosses the alert line. Click one to inspect it.</p>

      <ol className="alert-feed__list">
        {visible.length === 0 && <li className="empty">No alerts yet.</li>}
        {visible.map((alert) => {
          const created = new Date(alert.created_at);
          return (
            <li key={alert.id}>
              <button
                className={`alert-item ${alert.node_id === selectedNode ? "is-selected" : ""}`}
                onClick={() => onSelectNode(alert.node_id)}
                title={created.toLocaleString()}
              >
                <span className={`alert-item__severity status--${alert.severity}`}>
                  <StatusIcon status={alert.severity} />
                </span>
                <span className="alert-item__body">
                  <span className="alert-item__title">
                    Node {alert.node_id} · {METRIC_LABEL[alert.metric] ?? alert.metric}
                  </span>
                  <span className="alert-item__meta">
                    {STATUS_LABEL[alert.severity]} · score {Number(alert.score).toFixed(2)}
                  </span>
                </span>
                <span className="alert-item__time">{timeAgo(created, now)}</span>
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
