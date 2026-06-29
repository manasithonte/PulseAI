import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export default function MetricChart({ title, data, dataKey, color, unit }) {
  const formatted = data.map((d) => ({
    ...d,
    timeLabel: new Date(d.ts * 1000).toLocaleTimeString(),
  }));

  return (
    <div className="metric-chart">
      <h4>{title}</h4>
      <ResponsiveContainer width="100%" height={160}>
        <LineChart data={formatted}>
          <CartesianGrid strokeDasharray="3 3" stroke="#2a2a35" />
          <XAxis dataKey="timeLabel" tick={{ fontSize: 10 }} minTickGap={30} />
          <YAxis tick={{ fontSize: 10 }} width={40} />
          <Tooltip formatter={(value) => [`${Number(value).toFixed(2)}${unit ?? ""}`, title]} />
          <Line type="monotone" dataKey={dataKey} stroke={color} dot={false} strokeWidth={2} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
