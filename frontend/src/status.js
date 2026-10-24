export const WARNING_THRESHOLD = 0.6; // the shipped models' alert threshold
export const CRITICAL_THRESHOLD = 0.85; // matches backend consumer.CRITICAL_THRESHOLD

export function statusFor(score) {
  if (score === undefined || score === null) return "unknown";
  if (score > CRITICAL_THRESHOLD) return "critical";
  if (score > WARNING_THRESHOLD) return "warning";
  return "healthy";
}

export const STATUS_LABEL = {
  healthy: "Healthy",
  warning: "Warning",
  critical: "Critical",
  unknown: "No data",
};

// `scale` converts the raw backend value to the displayed unit (error_rate is a fraction).
export const METRICS = [
  { key: "cpu", label: "CPU", unit: "%", scale: 1, digits: 1 },
  { key: "memory", label: "Memory", unit: "%", scale: 1, digits: 1 },
  { key: "latency_ms", label: "Latency", unit: "ms", scale: 1, digits: 0 },
  { key: "error_rate", label: "Error rate", unit: "%", scale: 100, digits: 1 },
];

export const METRIC_LABEL = Object.fromEntries(METRICS.map((m) => [m.key, m.label]));

export function formatTime(ts) {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function timeAgo(date, now = Date.now()) {
  const seconds = Math.max(0, Math.round((now - date.getTime()) / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.floor(minutes / 60)}h ago`;
}
