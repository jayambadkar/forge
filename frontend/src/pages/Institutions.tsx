import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { fetchInstitutions } from "../api";
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
    <>
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
              <strong className="figure">{row.cases.toLocaleString("en-GB")}</strong>
              <div className="bar" aria-hidden="true">
                <span
                  style={{ width: `${(row.close / total) * 100}%`, background: "var(--green)" }}
                />
                <span
                  style={{ width: `${(row.rfi / total) * 100}%`, background: "var(--orange)" }}
                />
                <span
                  style={{ width: `${(row.escalate / total) * 100}%`, background: "var(--red)" }}
                />
              </div>
              <p className="meta">
                {row.close} close · {row.rfi} RFI · {row.escalate} escalate
              </p>
              <ul>
                {row.reasons.slice(0, 5).map((reason) => (
                  <li key={reason.code}>
                    <span className="code-tag">{reason.code}</span>{" "}
                    <span className="nums">{reason.count}</span>
                  </li>
                ))}
              </ul>
            </article>
          );
        })}
      </div>
    </>
  );
}
