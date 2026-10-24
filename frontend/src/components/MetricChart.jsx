import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { formatTime } from "../status";
import ChartTooltip from "./ChartTooltip";

const AXIS_TICK = { fontSize: 10, fill: "var(--muted)" };

export default function MetricChart({ metric, data }) {
  const { key, label, unit, scale, digits } = metric;
  const values = data.map((d) => d[key] * scale).filter(Number.isFinite);
  const fmt = (v) => `${Number(v).toFixed(digits)}${unit === "%" ? "%" : ` ${unit}`}`;
  const current = values.at(-1);

  return (
    <div className="metric-card">
      <div className="metric-card__header">
        <span className="metric-card__label">{label}</span>
        <span className="metric-card__value">{current !== undefined ? fmt(current) : "--"}</span>
      </div>
      <div className="metric-card__range">
        {values.length ? `min ${fmt(Math.min(...values))} · max ${fmt(Math.max(...values))}` : "No data yet"}
      </div>
      <ResponsiveContainer width="100%" height={130}>
        <LineChart data={data} margin={{ top: 6, right: 24, bottom: 0, left: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis
            dataKey="ts"
            type="number"
            domain={["dataMin", "dataMax"]}
            tickFormatter={formatTime}
            tick={AXIS_TICK}
            stroke="var(--axis)"
            minTickGap={40}
          />
          <YAxis tick={AXIS_TICK} stroke="var(--axis)" width={36} tickLine={false} axisLine={false} />
          <Tooltip
            content={<ChartTooltip format={fmt} />}
            cursor={{ stroke: "var(--ink-2)", strokeWidth: 1 }}
            isAnimationActive={false}
          />
          <Line
            dataKey={(d) => d[key] * scale}
            stroke="var(--series-1)"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, stroke: "var(--surface)", strokeWidth: 2 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
