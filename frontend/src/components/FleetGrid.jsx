function statusFor(score) {
  if (score === undefined) return "unknown";
  if (score > 0.85) return "critical";
  if (score > 0.6) return "warning";
  return "healthy";
}

export default function FleetGrid({ nodeIds, scores, selectedNode, onSelectNode }) {
  return (
    <div className="fleet-grid">
      {nodeIds.map((nodeId) => {
        const score = scores[nodeId];
        const status = statusFor(score);
        return (
          <button
            key={nodeId}
            className={`node-card node-card--${status} ${selectedNode === nodeId ? "node-card--selected" : ""}`}
            onClick={() => onSelectNode(nodeId)}
          >
            <div className="node-card__id">#{nodeId}</div>
            <div className="node-card__score">{score !== undefined ? score.toFixed(2) : "--"}</div>
          </button>
        );
      })}
    </div>
  );
}
