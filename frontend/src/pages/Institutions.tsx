import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchInstitutions } from "../api";
import { reasonLabel } from "../format";
import type { Institution } from "../types";

export function Institutions() {
  const [rows, setRows] = useState<Institution[]>([]);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchInstitutions()
      .then(setRows)
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
  if (rows.length === 0) return <p>Loading institutions…</p>;

  return (
    <div className="overview">
      <p className="crumbs">Forge / Institutions</p>
      <h1>Institutions</h1>
      <p className="lede">
        Each firm is scored with its own standard. One verdict covers every alert on the case.
      </p>
      <div className="firm-grid">
        {rows.map((row) => {
          const total = Math.max(1, row.close + row.rfi + row.escalate);
          return (
            <article className="firm-card" key={row.id}>
              <h2>
                <Link to={`/?institution=${row.id}`}>{row.label}</Link>
              </h2>
              <p className="kpi-label">Cases</p>
              <p className="kpi-value nums">{row.cases.toLocaleString("en-GB")}</p>
              <span className="stack" aria-hidden="true">
                <i className="close" style={{ width: `${(row.close / total) * 100}%` }} />
                <i className="rfi" style={{ width: `${(row.rfi / total) * 100}%` }} />
                <i className="escalate" style={{ width: `${(row.escalate / total) * 100}%` }} />
              </span>
              <p className="kpi-note nums">
                {row.close.toLocaleString("en-GB")} close · {row.rfi.toLocaleString("en-GB")} RFI ·{" "}
                {row.escalate.toLocaleString("en-GB")} escalate
              </p>
              <p className="firm-sub">Most common reasons</p>
              <ul className="reason-counts">
                {row.reasons.slice(0, 5).map((reason) => (
                  <li key={reason.code}>
                    <span title={reason.code}>{reasonLabel(reason.code)}</span>
                    <span className="nums">{reason.count.toLocaleString("en-GB")}</span>
                  </li>
                ))}
              </ul>
            </article>
          );
        })}
      </div>
    </div>
  );
}
