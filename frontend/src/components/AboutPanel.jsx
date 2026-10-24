import { CRITICAL_THRESHOLD, WARNING_THRESHOLD } from "../status";
import StatusIcon from "./StatusIcon";

export default function AboutPanel({ nodeCount, onClose }) {
  return (
    <section className="about" aria-labelledby="about-title">
      <div className="about__intro">
        <h2 id="about-title">What is PulseAI?</h2>
        <p>
          PulseAI watches a fleet of servers and uses machine learning to spot the ones behaving abnormally, in real
          time. When a server's behavior looks unusual, it raises an alert, so problems are caught before users notice
          them.
        </p>
        <button className="about__close" onClick={onClose} aria-label="Hide this explanation">
          Got it
        </button>
      </div>

      <div className="about__grid">
        <div className="about__item">
          <h3>What is a node?</h3>
          <p>
            A <strong>node</strong> is one server (machine) in the fleet. This demo simulates {nodeCount || 50} of
            them. Each reports its CPU, memory, latency and error rate twice per second.
          </p>
        </div>
        <div className="about__item">
          <h3>What is the anomaly score?</h3>
          <p>
            An ML model (Isolation Forest by default) compares each node's last 60 seconds of metrics against what normal looks
            like, and gives it a score from <strong>0</strong> (normal) to <strong>1</strong> (very unusual).
          </p>
        </div>
        <div className="about__item">
          <h3>How do I read the colors?</h3>
          <ul className="about__legend">
            <li>
              <StatusIcon status="healthy" />
              <span><strong>Healthy</strong>: score {WARNING_THRESHOLD} or below</span>
            </li>
            <li>
              <StatusIcon status="warning" />
              <span><strong>Warning</strong>: above {WARNING_THRESHOLD}, an alert is raised</span>
            </li>
            <li>
              <StatusIcon status="critical" />
              <span><strong>Critical</strong>: above {CRITICAL_THRESHOLD}, alert + email</span>
            </li>
          </ul>
        </div>
        <div className="about__item">
          <h3>What can I do here?</h3>
          <p>
            Click any node, or any alert, to see that node's metrics and score over time. The simulator injects
            occasional spikes, so new alerts appear every few seconds.
          </p>
        </div>
      </div>
    </section>
  );
}
