import { STATUS_LABEL } from "../status";

// Shape differs per status so state never relies on color alone.
export default function StatusIcon({ status, size = 12 }) {
  const common = { width: size, height: size, viewBox: "0 0 12 12", "aria-hidden": true, className: `status-icon status--${status}` };
  if (status === "critical") {
    return (
      <svg {...common}>
        <path d="M4 0.5h4L11.5 4v4L8 11.5H4L0.5 8V4z" fill="currentColor" />
        <path d="M6 3v3.5M6 8.6v.1" stroke="var(--surface)" strokeWidth="1.6" strokeLinecap="round" />
      </svg>
    );
  }
  if (status === "warning") {
    return (
      <svg {...common}>
        <path d="M6 0.8l5.4 10H0.6z" fill="currentColor" strokeLinejoin="round" />
        <path d="M6 4.3v3M6 9v.1" stroke="var(--surface)" strokeWidth="1.5" strokeLinecap="round" />
      </svg>
    );
  }
  if (status === "healthy") {
    return (
      <svg {...common}>
        <circle cx="6" cy="6" r="5.5" fill="currentColor" />
        <path d="M3.5 6.2l1.7 1.6 3.3-3.4" fill="none" stroke="var(--surface)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  return (
    <svg {...common}>
      <circle cx="6" cy="6" r="4.75" fill="none" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}

export function StatusBadge({ status }) {
  return (
    <span className={`status-badge status-badge--${status}`}>
      <StatusIcon status={status} />
      {STATUS_LABEL[status]}
    </span>
  );
}
