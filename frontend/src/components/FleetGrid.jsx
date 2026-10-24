import { STATUS_LABEL, statusFor } from "../status";
import StatusIcon from "./StatusIcon";

const LEGEND = ["healthy", "warning", "critical"];
const FLAGGED = ["warning", "critical"];

export default function FleetGrid({ nodeIds, scores, selectedNode, onSelectNode, filter, onFilterChange }) {
  const visible = filter === "flagged" ? nodeIds.filter((id) => FLAGGED.includes(statusFor(scores[id]))) : nodeIds;

  return (
    <div className="panel">
      <div className="panel__header">
        <h2>
          Fleet <span className="panel__count">{nodeIds.length} nodes</span>
        </h2>
        <div className="panel__tools">
          <ul className="legend" aria-label="Status legend">
            {LEGEND.map((s) => (
              <li key={s}>
                <StatusIcon status={s} />
                {STATUS_LABEL[s]}
              </li>
            ))}
          </ul>
          <div className="segmented" role="group" aria-label="Filter nodes">
            {["all", "flagged"].map((f) => (
              <button key={f} className={filter === f ? "is-active" : ""} onClick={() => onFilterChange(f)}>
                {f === "all" ? "All" : "Flagged"}
              </button>
            ))}
          </div>
        </div>
      </div>

      <p className="panel__description">
        Each card is one <strong>node</strong> (a server). The number is its anomaly score: 0 is normal, 1 is very
        unusual. Click a card to see its metrics.
      </p>

      {visible.length === 0 ? (
        <div className="empty">{nodeIds.length ? "No flagged nodes right now." : "Waiting for nodes to report…"}</div>
      ) : (
        <div className="fleet-grid">
          {visible.map((nodeId) => {
            const score = scores[nodeId];
            const status = statusFor(score);
            return (
              <button
                key={nodeId}
                className={`node-card node-card--${status} ${selectedNode === nodeId ? "is-selected" : ""}`}
                onClick={() => onSelectNode(nodeId)}
                aria-pressed={selectedNode === nodeId}
                aria-label={`Node ${nodeId}, ${STATUS_LABEL[status]}${score !== undefined ? `, score ${score.toFixed(2)}` : ""}`}
              >
                <span className="node-card__top">
                  <span className="node-card__id">#{nodeId}</span>
                  <StatusIcon status={status} size={11} />
                </span>
                <span className="node-card__score">{score !== undefined ? score.toFixed(2) : "--"}</span>
                <span className="node-card__bar">
                  <span style={{ width: `${Math.round((score ?? 0) * 100)}%` }} />
                </span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
