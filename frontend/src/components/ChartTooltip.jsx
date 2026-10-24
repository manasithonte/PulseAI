import { formatTime } from "../status";

export default function ChartTooltip({ active, payload, label, format }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="chart-tooltip">
      <div className="chart-tooltip__time">{formatTime(label)}</div>
      <div className="chart-tooltip__value">{format(payload[0].value)}</div>
    </div>
  );
}
