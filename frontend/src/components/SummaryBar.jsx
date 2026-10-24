import StatusIcon from "./StatusIcon";

const RECENT_ALERT_WINDOW_MS = 5 * 60 * 1000;

function Tile({ label, value, detail, status }) {
  return (
    <div className="stat-tile">
      <div className="stat-tile__label">
        {status && <StatusIcon status={status} />}
        {label}
      </div>
      <div className="stat-tile__value">{value}</div>
      {detail && <div className="stat-tile__detail">{detail}</div>}
    </div>
  );
}

export default function SummaryBar({ counts, total, alerts, alertLimit }) {
  const now = Date.now();
  const recent = alerts.filter((a) => now - new Date(a.created_at).getTime() < RECENT_ALERT_WINDOW_MS);
  const recentCritical = recent.filter((a) => a.severity === "critical").length;
  const pct = (n) => (total ? `${Math.round((n / total) * 100)}% of fleet` : "--");

  return (
    <div className="summary-bar">
      <Tile label="Healthy" status="healthy" value={counts.healthy} detail={pct(counts.healthy)} />
      <Tile label="Warning" status="warning" value={counts.warning} detail={pct(counts.warning)} />
      <Tile label="Critical" status="critical" value={counts.critical} detail={pct(counts.critical)} />
      <Tile
        label="Alerts · last 5 min"
        value={recent.length >= alertLimit ? `${alertLimit}+` : recent.length}
        detail={`${recentCritical} critical`}
      />
    </div>
  );
}
