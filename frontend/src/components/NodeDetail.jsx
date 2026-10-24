import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CRITICAL_THRESHOLD, METRICS, WARNING_THRESHOLD, formatTime, statusFor } from "../status";
import ChartTooltip from "./ChartTooltip";
import MetricChart from "./MetricChart";
import { StatusBadge } from "./StatusIcon";

const AXIS_TICK = { fontSize: 10, fill: "var(--muted)" };

function ScoreChart({ data }) {
  return (
    <div className="metric-card metric-card--wide">
      <div className="metric-card__header">
        <span className="metric-card__label">Anomaly score</span>
        <span className="metric-card__hint">
          alerts above {WARNING_THRESHOLD} · critical above {CRITICAL_THRESHOLD}
        </span>
      </div>
      {data.length < 2 ? (
        <div className="empty empty--chart">Collecting live scores…</div>
      ) : (
        <ResponsiveContainer width="100%" height={150}>
          <LineChart data={data} margin={{ top: 8, right: 64, bottom: 0, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis
              dataKey="ts"
              type="number"
              domain={["dataMin", "dataMax"]}
              tickFormatter={formatTime}
              tick={AXIS_TICK}
              stroke="var(--axis)"
              minTickGap={60}
            />
            <YAxis domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} tick={AXIS_TICK} width={36} tickLine={false} axisLine={false} />
            <ReferenceLine
              y={WARNING_THRESHOLD}
              stroke="var(--status-warning)"
              strokeDasharray="4 4"
              label={{ value: "Alert", position: "right", fill: "var(--ink-2)", fontSize: 10 }}
            />
            <ReferenceLine
              y={CRITICAL_THRESHOLD}
              stroke="var(--status-critical)"
              strokeDasharray="4 4"
              label={{ value: "Critical", position: "right", fill: "var(--ink-2)", fontSize: 10 }}
            />
            <Tooltip
              content={<ChartTooltip format={(v) => Number(v).toFixed(2)} />}
              cursor={{ stroke: "var(--ink-2)", strokeWidth: 1 }}
              isAnimationActive={false}
            />
            <Line
              dataKey="score"
              stroke="var(--series-1)"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, stroke: "var(--surface)", strokeWidth: 2 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

export default function NodeDetail({ nodeId, score, scoreHistory, history }) {
  if (nodeId === null) {
    return (
      <div className="panel">
        <div className="empty">Select a node to see its metrics.</div>
      </div>
    );
  }
  return (
    <div className="panel">
      <div className="panel__header">
        <h2>Node {nodeId}</h2>
        <div className="panel__tools">
          <StatusBadge status={statusFor(score)} />
          <span className="node-detail__score">
            score <strong>{score !== undefined ? score.toFixed(2) : "--"}</strong>
          </span>
        </div>
      </div>
      <p className="panel__description">
        The anomaly score over time, followed by the four raw metrics the model watches. A spike in the metrics pushes
        the score above the alert line.
      </p>
      <ScoreChart data={scoreHistory} />
      <div className="metric-grid">
        {METRICS.map((m) => (
          <MetricChart key={m.key} metric={m} data={history} />
        ))}
      </div>
    </div>
  );
}
