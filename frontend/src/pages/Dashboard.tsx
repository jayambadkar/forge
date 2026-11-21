import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchDashboard } from "../api";
import type { DashboardStats } from "../types";

export function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchDashboard()
      .then(setStats)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Request failed");
      });
  }, []);

  if (error)
    return (
      <div className="banner escalate" role="alert">
        {error}
      </div>
    );
  if (!stats) return <p>Loading the desk…</p>;

  const verdicts = [
    { label: "Close", value: stats.close, color: "var(--green)" },
    { label: "Ask", value: stats.rfi, color: "var(--orange)" },
    { label: "Escalate", value: stats.escalate, color: "var(--red)" },
  ];

  return (
    <>
      <p className="crumbs">Forge / Dashboard</p>
      <h1>Desk</h1>
      <p className="lede">Open work across the four firms.</p>
      <div className="stat-grid">
        <article className="stat">
          <p className="caption">Open</p>
          <strong>{stats.open.toLocaleString("en-GB")}</strong>
        </article>
        <article className="stat">
          <p className="caption">With the MLRO</p>
          <strong>{stats.escalated.toLocaleString("en-GB")}</strong>
        </article>
        <article className="stat">
          <p className="caption">Open over 30 days</p>
          <strong>{stats.ageing.toLocaleString("en-GB")}</strong>
        </article>
        <article className="stat">
          <p className="caption">Not yet decided</p>
          <strong>{stats.new.toLocaleString("en-GB")}</strong>
        </article>
      </div>
      <article className="panel">
        <h2>Recommendations</h2>
        <Chart items={verdicts} />
      </article>
      <p>
        <Link to="/">Open the case queue</Link>
      </p>
    </>
  );
}

function Chart({ items }: { items: { label: string; value: number; color: string }[] }) {
  const max = Math.max(1, ...items.map((item) => item.value));
  return (
    <svg viewBox="0 0 460 120" role="img" aria-label="Recommendations">
      {items.map((item, index) => (
        <g key={item.label} transform={`translate(0 ${index * 36})`}>
          <text y="18" fontSize="16" fill="#0b0c0c">
            {item.label}
          </text>
          <rect x="110" y="4" height="16" width={(item.value / max) * 260} fill={item.color} />
          <text x="380" y="18" fontSize="16" fill="#484949">
            {item.value.toLocaleString("en-GB")}
          </text>
        </g>
      ))}
    </svg>
  );
}
