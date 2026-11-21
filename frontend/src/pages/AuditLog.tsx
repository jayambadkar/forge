import { useEffect, useState } from "react";
import { fetchAudit } from "../api";
import { AuditEntry } from "../components/AuditEntry";
import { ExportMenu } from "../components/ExportMenu";
import type { AuditEvent } from "../types";

export function AuditLog() {
  const [rows, setRows] = useState<AuditEvent[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [kind, setKind] = useState("");
  const [institution, setInstitution] = useState("");
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");

  useEffect(() => {
    setLoading(true);
    fetchAudit({ kind, institution, q, limit: 200 })
      .then(setRows)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Request failed");
      })
      .finally(() => setLoading(false));
  }, [kind, institution, q]);

  const filters = { kind, institution, q };

  return (
    <>
      <p className="crumbs">Forge / Audit log</p>
      <h1>Audit log</h1>
      <p className="lede">
        Append-only. Policy decisions, analyst changes and batch jobs stay in the order they were
        written.
      </p>
      {error ? (
        <div className="banner escalate" role="alert">
          {error}
        </div>
      ) : null}
      <div className="toolbar">
        <select aria-label="Kind" value={kind} onChange={(event) => setKind(event.target.value)}>
          <option value="">All events</option>
          <option value="ai">Policy engine</option>
          <option value="model">Model cross-check</option>
          <option value="human">Analyst</option>
          <option value="system">Batch jobs</option>
        </select>
        <select
          aria-label="Institution"
          value={institution}
          onChange={(event) => setInstitution(event.target.value)}
        >
          <option value="">All firms</option>
          <option value="bank">Retail bank</option>
          <option value="emoney">E-money</option>
          <option value="investment">Investment</option>
          <option value="payments_fx">Payments & FX</option>
        </select>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            setQ(search);
          }}
        >
          <input
            aria-label="Search the log"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Case, analyst or code"
          />
        </form>
        <ExportMenu params={filters} />
      </div>
      {loading ? <p>Loading the log…</p> : null}
      {!loading && rows.length === 0 ? <p>No events match these filters.</p> : null}
      <ol className="audit-list">
        {rows.map((event) => (
          <AuditEntry key={event.id} event={event} showCase />
        ))}
      </ol>
    </>
  );
}
