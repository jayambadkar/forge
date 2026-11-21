import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { fetchCases, fetchInstitutions } from "../api";
import { ExportMenu } from "../components/ExportMenu";
import { VerdictPill } from "../components/Verdict";
import { gbp, labelFor, openLabel } from "../format";
import type { CaseSummary, Institution } from "../types";

const INSTITUTIONS = ["bank", "emoney", "investment", "payments_fx"];
const RULES = ["TM01", "TM02", "TM03", "TM04", "TM05", "TM06", "TM07", "TM08", "TM10", "TM22"];
const PAGE = 25;

export function Queue() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const institution = params.get("institution") ?? "bank";
  const verdict = params.get("verdict") ?? "";
  const reason = params.get("reason") ?? "";
  const rule = params.get("rule") ?? "";
  const risk = params.get("risk") ?? "";
  const status = params.get("status") ?? "";
  const sort = params.get("sort") ?? "sla";
  const q = params.get("q") ?? "";
  const page = Math.max(1, Number(params.get("page") ?? "1") || 1);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [rows, setRows] = useState<CaseSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState(q);
  const [selected, setSelected] = useState(0);

  useEffect(() => {
    fetchInstitutions()
      .then(setInstitutions)
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Request failed");
      });
  }, []);

  useEffect(() => {
    setLoading(true);
    setError("");
    fetchCases({
      institution,
      verdict,
      reason,
      q,
      rule,
      risk,
      status,
      sort,
      limit: PAGE,
      offset: (page - 1) * PAGE,
    })
      .then((payload) => {
        setRows(payload.cases);
        setTotal(payload.total);
        setSelected(0);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Request failed");
      })
      .finally(() => setLoading(false));
  }, [institution, verdict, reason, q, rule, risk, status, sort, page]);

  const current = institutions.find((item) => item.id === institution);
  const reasons = useMemo(() => current?.reasons ?? [], [current]);
  const pages = Math.max(1, Math.ceil(total / PAGE));
  const moreOn = Boolean(reason || rule || risk || status || (sort && sort !== "sla"));

  function set(next: Record<string, string>) {
    const merged = new URLSearchParams(params);
    for (const [key, value] of Object.entries(next)) {
      if (value) merged.set(key, value);
      else merged.delete(key);
    }
    if (!("page" in next)) merged.delete("page");
    setParams(merged);
  }

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const tag = (event.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;
      if (event.key === "j") {
        event.preventDefault();
        setSelected((index) => Math.min(rows.length - 1, index + 1));
      }
      if (event.key === "k") {
        event.preventDefault();
        setSelected((index) => Math.max(0, index - 1));
      }
      if (event.key === "Enter" && rows[selected]) {
        event.preventDefault();
        void navigate(`/cases/${rows[selected].institution}/${rows[selected].caseId}`);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate, rows, selected]);

  const filters: Record<string, string> = {};
  params.forEach((value, key) => {
    if (key !== "page") filters[key] = value;
  });

  return (
    <>
      <p className="crumbs">Forge / Case queue</p>
      <h1>{labelFor(institution)}</h1>
      <p className="lede">
        {loading ? "Loading the queue…" : `${total.toLocaleString("en-GB")} cases`}
      </p>
      {error ? (
        <div className="banner escalate" role="alert">
          {error}
        </div>
      ) : null}
      <div className="toolbar">
        <form
          onSubmit={(event) => {
            event.preventDefault();
            set({ q: search });
          }}
        >
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search"
            aria-label="Search"
            style={{ width: "14rem" }}
          />
        </form>
        <select
          aria-label="Verdict"
          value={verdict}
          onChange={(event) => set({ verdict: event.target.value })}
        >
          <option value="">All recommendations</option>
          <option value="CLOSE">Close</option>
          <option value="RFI">Ask</option>
          <option value="ESCALATE">Escalate</option>
        </select>
        <select
          aria-label="Institution"
          value={institution}
          onChange={(event) => set({ institution: event.target.value, reason: "" })}
        >
          {INSTITUTIONS.map((id) => (
            <option key={id} value={id}>
              {labelFor(id)}
            </option>
          ))}
        </select>
        <ExportMenu params={filters} />
      </div>
      <details className="more" open={moreOn}>
        <summary>More filters</summary>
        <div className="toolbar">
          <select
            aria-label="Reason code"
            value={reason}
            onChange={(event) => set({ reason: event.target.value })}
          >
            <option value="">All reasons</option>
            {reasons.map((item) => (
              <option key={item.code} value={item.code}>
                {item.code}
              </option>
            ))}
          </select>
          <select
            aria-label="Rule"
            value={rule}
            onChange={(event) => set({ rule: event.target.value })}
          >
            <option value="">All rules</option>
            {RULES.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
          <select
            aria-label="Score band"
            value={risk}
            onChange={(event) => set({ risk: event.target.value })}
          >
            <option value="">Any score</option>
            <option value="high">Higher</option>
            <option value="review">Middle</option>
            <option value="low">Lower</option>
          </select>
          <select
            aria-label="Status"
            value={status}
            onChange={(event) => set({ status: event.target.value })}
          >
            <option value="">Any status</option>
            <option value="New">New</option>
            <option value="In review">In review</option>
            <option value="Decided">Decided</option>
            <option value="Escalated / MLRO">With the MLRO</option>
          </select>
          <select
            aria-label="Sort"
            value={sort}
            onChange={(event) => set({ sort: event.target.value })}
          >
            <option value="sla">Longest open</option>
            <option value="opened">Newest</option>
            <option value="amount">Largest amount</option>
            <option value="customer">Customer name</option>
          </select>
        </div>
      </details>
      {loading ? <p>Loading the queue…</p> : null}
      {!loading && rows.length === 0 ? <p>No cases match these filters.</p> : null}
      <div className="cards">
        {rows.map((row, index) => (
          <Link
            key={row.caseId}
            className={`case-card ${row.verdict.toLowerCase()} ${index === selected ? "selected" : ""}`}
            to={`/cases/${row.institution}/${row.caseId}`}
          >
            <div className="card-top">
              <h2>
                {row.customerName || row.customerId} <VerdictPill verdict={row.verdict} />
              </h2>
              <span className="card-amount nums">{gbp(row.amount)}</span>
            </div>
            <p className="reason-line">{(row.reason || "").split(/(?<=[.!?])\s/)[0]}</p>
            <p className="meta">{openLabel(row.openedAt)}</p>
          </Link>
        ))}
      </div>
      <div className="pager">
        <button type="button" disabled={page <= 1} onClick={() => set({ page: String(page - 1) })}>
          Previous
        </button>
        <span className="nums">
          Page {page} of {pages}
        </span>
        <button
          type="button"
          disabled={page >= pages}
          onClick={() => set({ page: String(page + 1) })}
        >
          Next
        </button>
      </div>
    </>
  );
}
