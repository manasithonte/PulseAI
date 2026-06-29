export default function AlertFeed({ alerts }) {
  return (
    <div className="alert-feed">
      <h3>Alerts</h3>
      <div className="alert-feed__list">
        {alerts.length === 0 && <div className="alert-feed__empty">No alerts yet.</div>}
        {alerts.map((alert) => (
          <div key={alert.id} className={`alert-item alert-item--${alert.severity}`}>
            <span className="alert-item__time">{new Date(alert.created_at).toLocaleTimeString()}</span>
            <span className="alert-item__node">Node {alert.node_id}</span>
            <span className="alert-item__metric">{alert.metric}</span>
            <span className="alert-item__score">{Number(alert.score).toFixed(2)}</span>
            <span className={`alert-item__badge alert-item__badge--${alert.severity}`}>{alert.severity}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
