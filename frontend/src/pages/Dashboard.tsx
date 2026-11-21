import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchDashboard, fetchInstitutions } from "../api";
import { reasonLabel, when } from "../format";
import type { DashboardStats, Institution } from "../types";

export function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [firms, setFirms] = useState<Institution[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([fetchDashboard(), fetchInstitutions()])
      .then(([dashboard, institutions]) => {
        setStats(dashboard);
        setFirms(institutions);
      })
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

  const share = (value: number) => (stats.cases ? Math.round((value / stats.cases) * 100) : 0);
  const reasons = new Map<string, number>();
  for (const firm of firms) {
    for (const item of firm.reasons)
      reasons.set(item.code, (reasons.get(item.code) ?? 0) + item.count);
  }
  const topReasons = [...reasons.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
  const topMax = Math.max(1, ...topReasons.map(([, count]) => count));
  const ages = [
    { label: "0 to 30 days", value: stats.sla0 },
    { label: "31 to 60 days", value: stats.sla1 },
    { label: "61 to 90 days", value: stats.sla2 },
    { label: "Over 90 days", value: stats.sla3 },
  ];
  const ageMax = Math.max(1, ...ages.map((item) => item.value));

  return (
    <>
      <p className="crumbs">Forge / Dashboard</p>
      <h1>Desk</h1>
      <p className="lede">
        {stats.cases.toLocaleString("en-GB")} cases across {firms.length || 4} firms. Figures as of{" "}
        {when(stats.syncedAt)}.
      </p>

      <h2>Recommendations</h2>
      <div className="kpis">
        <Kpi
          label="Close"
          value={stats.close}
          note={`${share(stats.close)}% of cases`}
          tone="close"
        />
        <Kpi
          label="Request information"
          value={stats.rfi}
          note={`${share(stats.rfi)}% of cases`}
          tone="rfi"
        />
        <Kpi
          label="Escalate to MLRO"
          value={stats.escalate}
          note={`${share(stats.escalate)}% of cases`}
          tone="escalate"
        />
        <Kpi
          label="Closes the model doubts"
          value={stats.wrongfulCloseRisk}
          note="Close recommended, model gives escalation 20% or more"
        />
      </div>

      <h2>Work</h2>
      <div className="kpis">
        <Kpi label="Open" value={stats.open} note="Not yet decided by an analyst" />
        <Kpi label="With the MLRO" value={stats.escalated} note="Routed automatically" />
        <Kpi label="In review" value={stats.inReview} note="Owned by an analyst" />
        <Kpi label="Decided" value={stats.decided} note="Accepted or overridden" />
      </div>

      <div className="dash-grid">
        <article className="panel">
          <h2>By firm</h2>
          <table>
            <thead>
              <tr>
                <th>Firm</th>
                <th className="num">Cases</th>
                <th>Mix</th>
                <th className="num">Close</th>
                <th className="num">Request</th>
                <th className="num">Escalate</th>
              </tr>
            </thead>
            <tbody>
              {firms.map((firm) => {
                const total = Math.max(1, firm.close + firm.rfi + firm.escalate);
                return (
                  <tr key={firm.id}>
                    <td>
                      <Link to={`/?institution=${firm.id}`}>{firm.label}</Link>
                    </td>
                    <td className="num nums">{firm.cases.toLocaleString("en-GB")}</td>
                    <td>
                      <span className="stack" aria-label="Recommendation mix">
                        <i className="close" style={{ width: `${(firm.close / total) * 100}%` }} />
                        <i className="rfi" style={{ width: `${(firm.rfi / total) * 100}%` }} />
                        <i
                          className="escalate"
                          style={{ width: `${(firm.escalate / total) * 100}%` }}
                        />
                      </span>
                    </td>
                    <td className="num nums">{firm.close.toLocaleString("en-GB")}</td>
                    <td className="num nums">{firm.rfi.toLocaleString("en-GB")}</td>
                    <td className="num nums">{firm.escalate.toLocaleString("en-GB")}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </article>

        <article className="panel">
          <h2>Age of open cases</h2>
          <dl className="bars">
            {ages.map((item) => (
              <div key={item.label} className="bar-row">
                <dt>{item.label}</dt>
                <dd>
                  <span className="bar neutral">
                    <i style={{ width: `${(item.value / ageMax) * 100}%` }} />
                  </span>
                  <span className="nums">{item.value.toLocaleString("en-GB")}</span>
                </dd>
              </div>
            ))}
          </dl>
        </article>

        <article className="panel wide">
          <h2>Most common reasons</h2>
          <dl className="bars">
            {topReasons.map(([code, count]) => (
              <div key={code} className="bar-row">
                <dt>{reasonLabel(code)}</dt>
                <dd>
                  <span
                    className={`bar ${code.startsWith("ESC_") ? "escalate" : code.startsWith("RFI_") ? "rfi" : "close"}`}
                  >
                    <i style={{ width: `${(count / topMax) * 100}%` }} />
                  </span>
                  <span className="nums">{count.toLocaleString("en-GB")}</span>
                </dd>
              </div>
            ))}
          </dl>
        </article>
      </div>

      <p>
        <Link to="/">Open the case queue</Link>
      </p>
    </>
  );
}

function Kpi({
  label,
  value,
  note,
  tone = "",
}: {
  label: string;
  value: number;
  note: string;
  tone?: string;
}) {
  return (
    <article className={`kpi ${tone}`}>
      <p className="kpi-label">{label}</p>
      <p className="kpi-value nums">{value.toLocaleString("en-GB")}</p>
      <p className="kpi-note">{note}</p>
    </article>
  );
}
