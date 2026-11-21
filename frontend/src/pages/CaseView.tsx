import { useEffect, useRef, useState, type SyntheticEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { act, fetchCase } from "../api";
import { ExportMenu } from "../components/ExportMenu";
import { AuditEntry } from "../components/AuditEntry";
import { CaseNav } from "../components/CaseNav";
import { Markdown } from "../components/Markdown";
import { CrossCheck, Recommendation, evidenceLookup } from "../components/Recommendation";
import { VerdictPill } from "../components/Verdict";
import { gbp, labelFor, mailto, openLabel, verdictLabel, when } from "../format";
import type { CaseDetail } from "../types";

const ANALYST = "Amira Okonkwo";

export function CaseView() {
  const { institution = "", caseId = "" } = useParams();
  const [params] = useSearchParams();
  const expand = params.get("expand") === "1";
  const [data, setData] = useState<CaseDetail | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState("");
  const [showAll, setShowAll] = useState(false);
  const [note, setNote] = useState("");
  const [override, setOverride] = useState("RFI");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState("");
  // Folds the analyst has opened or closed; unset folds follow ?expand=1.
  const [folds, setFolds] = useState<Record<string, boolean>>({});
  const [jumpTo, setJumpTo] = useState("");

  function load() {
    setError("");
    return fetchCase(institution, caseId)
      .then((detail) => {
        setData(detail);
        const cited = detail.evidence.find((doc) => doc.cited);
        setSelected(cited?.id || detail.evidence[0]?.id || "");
        document.title = `${detail.customer.name || detail.caseId} — Forge`;
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Request failed");
      });
  }

  useEffect(() => {
    setData(null);
    setDone("");
    void load();
    // load closes over the route params already listed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [institution, caseId]);

  useEffect(() => {
    if (!jumpTo) return;
    const target = document.getElementById(jumpTo);
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "center" });
      target.focus({ preventScroll: true });
    }
    setJumpTo("");
  }, [jumpTo]);

  function fold(name: string) {
    return {
      open: folds[name] ?? expand,
      onToggle: (event: SyntheticEvent<HTMLDetailsElement>) => {
        const isOpen = event.currentTarget.open;
        setFolds((current) =>
          current[name] === isOpen ? current : { ...current, [name]: isOpen },
        );
      },
    };
  }

  async function run(action: string, extra?: { verdict?: string; note?: string }) {
    setBusy(true);
    setError("");
    try {
      await act(institution, caseId, { action, actor: ANALYST, ...extra });
      setNote("");
      setDone(DONE[action] ?? "Saved.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The action failed");
    } finally {
      setBusy(false);
    }
  }

  if (error && !data)
    return (
      <div className="banner escalate" role="alert">
        {error}
      </div>
    );
  if (!data) return <p>Loading the case…</p>;

  const doc = data.evidence.find((item) => item.id === selected) ?? data.evidence[0];
  const citedDocs = data.evidence.filter((item) => item.cited).length;
  const timeline = showAll ? data.timeline : data.timeline.filter((txn) => txn.inAlert);
  const maxAmount = Math.max(1, ...timeline.map((txn) => txn.amount));
  const alertAmount = data.timeline
    .filter((txn) => txn.inAlert)
    .reduce((sum, txn) => sum + txn.amount, 0);
  const asks = (data.decision?.reason || "")
    .split(/(?<=[.!?])\s/)
    .filter((sentence) => sentence.startsWith("Ask"));
  const rfiBody = [
    `Dear ${data.customer.name || "customer"},`,
    "",
    `Please reply on case ${data.caseId}.`,
    asks.length
      ? asks.join(" ")
      : "Please send the document that explains the payments named in this review.",
    "",
    data.decision?.evidence?.length
      ? `Documents already on file: ${data.decision.evidence.join(", ")}.`
      : "",
    "",
    "Amira Okonkwo",
    "Forge",
  ].join("\n");
  const mlroBody = [
    `Escalation ${data.caseId} for ${data.customer.name}.`,
    data.decision?.reason || "",
    `Evidence: ${(data.decision?.evidence || []).join(", ") || "none cited"}.`,
    `Amount on the alert lines: ${gbp(alertAmount)}.`,
  ].join("\n");
  const email =
    data.decision?.verdict === "ESCALATE"
      ? {
          label: "Draft MLRO email",
          to: "mlro@forge.internal",
          subject: `Escalation ${data.caseId}`,
          body: mlroBody,
        }
      : {
          label: "Draft customer email",
          to: "",
          subject: `Information request ${data.caseId}`,
          body: rfiBody,
        };
  const describe = evidenceLookup(data);
  const showEvidence = (id: string) => {
    const ref = describe(id);
    if (!ref) return;
    if (ref.kind === "doc") {
      setSelected(id);
      setFolds((current) => ({ ...current, evidence: true }));
      setJumpTo(`ev-${id}`);
    } else if (ref.kind === "alert") {
      setFolds((current) => ({ ...current, alerts: true }));
      setJumpTo(`alert-${id}`);
    } else if (ref.kind === "txn") {
      if (!data.timeline.find((txn) => txn.id === id)?.inAlert) setShowAll(true);
      setFolds((current) => ({ ...current, transactions: true }));
      setJumpTo(`txn-${id}`);
    }
  };
  const submission = {
    case_id: data.caseId,
    alert_ids: data.alerts.map((alert) => alert.id),
    verdict: data.decision?.verdict ?? "",
    reason_code: data.decision?.reasonCode ?? "",
    reason: data.decision?.reason ?? "",
    evidence: data.decision?.evidence ?? [],
  };

  return (
    <>
      <p className="crumbs">
        <Link to="/">Case queue</Link> /{" "}
        <Link to={`/?institution=${institution}`}>{labelFor(institution)}</Link> /{" "}
        <span className="nums">{data.caseId}</span>
      </p>
      <CaseNav institution={institution} caseId={caseId} />
      <h1 className="case-title">
        <span>{data.customer.name || data.caseId}</span>
        <VerdictPill verdict={data.decision?.verdict ?? ""} />
      </h1>
      {error ? (
        <div className="banner escalate" role="alert">
          {error}
        </div>
      ) : null}
      <Recommendation data={data} amount={alertAmount} onSelect={showEvidence} />
      <p className="meta case-meta">
        {labelFor(institution)} · {openLabel(data.openedAt)} ·{" "}
        <span className="nums">{gbp(alertAmount)}</span>
        {data.work.status === "Escalated / MLRO" ? " · With the MLRO" : ""}
        {data.work.assignee ? ` · ${data.work.assignee}` : ""}
      </p>
      <div className="toolbar case-actions">
        <button
          type="button"
          className="primary"
          disabled={busy}
          title="Agree with Forge's recommendation. Saved to the audit trail under your name."
          onClick={() => {
            void run("accept");
          }}
        >
          Accept
        </button>
        <details className="menu">
          <summary title="Choose a different verdict. You must add a note saying why.">
            Override
          </summary>
          <form
            className="menu-form"
            onSubmit={(event) => {
              event.preventDefault();
              void run("override", { verdict: override, note });
            }}
          >
            <label>
              Verdict
              <select
                aria-label="Override verdict"
                value={override}
                onChange={(event) => setOverride(event.target.value)}
              >
                <option value="CLOSE">Close</option>
                <option value="RFI">Request information from the customer</option>
                <option value="ESCALATE">Escalate to the MLRO</option>
              </select>
            </label>
            <label>
              Note
              <input
                aria-label="Override note"
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="Why you are changing it"
                required
                minLength={8}
              />
            </label>
            <button type="submit" className="primary" disabled={busy}>
              Save override
            </button>
          </form>
        </details>
        <EmailDraft {...email} />
      </div>
      <AnalystDecision data={data} done={done} />

      <details className="fold" {...fold("case")}>
        <summary>
          <span className="fold-title">Case file</span>
          <span className="fold-meta">
            {data.customer.kind || "Customer"} · {data.work.assignee || "unassigned"}
          </span>
        </summary>
        <div className="fold-body">
          <dl className="summary">
            <div className="summary-row">
              <dt>Case</dt>
              <dd className="nums">{data.caseId}</dd>
            </div>
            <div className="summary-row">
              <dt>Customer</dt>
              <dd>
                {data.customer.name} ·{" "}
                {data.customer.occupation || data.customer.kind || "not recorded"}
              </dd>
            </div>
            <div className="summary-row">
              <dt>Expected monthly</dt>
              <dd className="nums">{gbp(data.customer.expectedMonthly)}</dd>
            </div>
            <div className="summary-row">
              <dt>Opened</dt>
              <dd>
                {openLabel(data.openedAt)}
                {data.heldPaymentId ? ` · held payment ${data.heldPaymentId}` : ""}
              </dd>
            </div>
            <div className="summary-row">
              <dt>Status</dt>
              <dd>
                {data.work.status}
                {data.work.decidedVerdict ? ` · ${data.work.decidedVerdict}` : ""}
                {data.work.note ? ` · ${data.work.note}` : ""}
              </dd>
            </div>
          </dl>
          <div className="toolbar">
            <button
              type="button"
              disabled={busy}
              title="Make yourself the owner of this case. Status changes to In review."
              onClick={() => {
                void run("assign");
              }}
            >
              Assign to me
            </button>
            <button
              type="button"
              disabled={busy}
              title="Record that you have sent the information request to the customer."
              onClick={() => {
                void run("rfi");
              }}
            >
              Mark request sent
            </button>
            <ExportMenu params={{ institution, q: data.caseId, caseId: data.caseId }} />
          </div>
        </div>
      </details>

      <details className="fold" {...fold("alerts")}>
        <summary>
          <span className="fold-title">Alerts</span>
          <span className="fold-meta">{data.alerts.length}</span>
        </summary>
        <div className="fold-body">
          {data.alerts.length === 0 ? (
            <p>No alerts on this case.</p>
          ) : (
            <div className="alert-list">
              {data.alerts.map((alert) => (
                <article key={alert.id} id={`alert-${alert.id}`} className="panel" tabIndex={-1}>
                  <p className="caption nums">
                    {alert.ruleId} · {alert.id}
                  </p>
                  <h2 className="panel-title">{alert.ruleName}</h2>
                  <p>{alert.message}</p>
                </article>
              ))}
            </div>
          )}
        </div>
      </details>

      <details className="fold" {...fold("transactions")}>
        <summary>
          <span className="fold-title">Transactions</span>
          <span className="fold-meta">
            {data.timeline.filter((txn) => txn.inAlert).length} on the alert
          </span>
        </summary>
        <div className="fold-body">
          <div className="toolbar">
            <button type="button" onClick={() => setShowAll((value) => !value)}>
              {showAll ? "Show alert lines only" : `Show full history (${data.timeline.length})`}
            </button>
          </div>
          {timeline.length === 0 ? (
            <p>No transactions in this view.</p>
          ) : (
            <ol className="timeline">
              {timeline.map((txn) => (
                <li key={txn.id} id={`txn-${txn.id}`} tabIndex={-1}>
                  <span>{when(txn.timestamp)}</span>
                  <span
                    title={`${txn.counterparty || "No counterparty name"} · ${txn.direction || "—"} · ${txn.channel || "—"}`}
                  >
                    {txn.counterparty || "No counterparty name"} · {txn.direction || "—"} ·{" "}
                    {txn.channel || "—"}
                  </span>
                  <span className="amount-bar" aria-hidden="true">
                    <i
                      style={{
                        width: `${(txn.amount / maxAmount) * 100}%`,
                        background: txn.direction === "out" ? "var(--red)" : "var(--green)",
                      }}
                    />
                  </span>
                  <span className="nums">{gbp(txn.amount)}</span>
                </li>
              ))}
            </ol>
          )}
        </div>
      </details>

      <details className="fold" {...fold("evidence")}>
        <summary>
          <span className="fold-title">Evidence</span>
          <span className="fold-meta">
            {plural(data.evidence.length, "document")}
            {citedDocs ? `, ${citedDocs} cited` : ""}
          </span>
        </summary>
        <div className="fold-body">
          {data.evidence.length === 0 ? (
            <p>No documents on file.</p>
          ) : (
            <div className="doc-layout">
              <div className="doc-nav">
                {data.evidence.map((item) => (
                  <button
                    key={item.id}
                    id={`ev-${item.id}`}
                    type="button"
                    aria-current={item.id === doc?.id}
                    onClick={() => setSelected(item.id)}
                  >
                    <strong className="doc-id nums">{item.id}</strong>
                    <span className="doc-kind">
                      {item.kind.replaceAll("_", " ")}
                      {item.cited ? " · cited" : ""}
                    </span>
                  </button>
                ))}
              </div>
              {doc ? (
                <article className={doc.cited ? "panel cited" : "panel"}>
                  <p className="caption">{doc.cited ? "Cited" : "On file"}</p>
                  <h2 className="doc-title">{doc.title || doc.id}</h2>
                  <Markdown
                    text={
                      withoutTitle(doc.text, doc.title) || "This document has no extracted text."
                    }
                  />
                </article>
              ) : null}
            </div>
          )}
        </div>
      </details>

      <details className="fold" {...fold("linked")}>
        <summary>
          <span className="fold-title">Linked cases</span>
          <span className="fold-meta">{data.related.length}</span>
        </summary>
        <div className="fold-body">
          {data.related.length === 0 ? (
            <p>No other case shares a counterparty, device, account, customer or list entry.</p>
          ) : (
            <ul className="linked-list">
              {data.related.map((item) => (
                <li key={`${item.institution}-${item.caseId}`}>
                  <Link to={`/cases/${item.institution}/${item.caseId}`}>
                    {item.customerName} · {item.caseId}
                  </Link>
                  <VerdictPill verdict={item.verdict} />
                  <span className="meta">
                    {item.link} · {item.via}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </details>

      <details className="fold" {...fold("crosscheck")}>
        <summary>
          <span
            className="fold-title hint"
            title="A separate model estimates each outcome from the case facts. It flags cases worth a second look and never changes the recommendation."
          >
            Model cross-check
          </span>
          <span className="fold-meta">{crossCheckSummary(data)}</span>
        </summary>
        <div className="fold-body">
          <CrossCheck data={data} />
        </div>
      </details>

      <details className="fold" {...fold("audit")}>
        <summary>
          <span className="fold-title">Audit trail</span>
          <span className="fold-meta">{plural(data.trail.length, "event")}</span>
        </summary>
        <div className="fold-body">
          {data.trail.length === 0 ? (
            <p>No events have been recorded for this case.</p>
          ) : (
            <ol className="audit-list">
              {data.trail.map((event) => (
                <AuditEntry
                  key={event.id}
                  event={event}
                  describe={describe}
                  onSelect={showEvidence}
                />
              ))}
            </ol>
          )}
        </div>
      </details>

      <details className="fold" {...fold("record")}>
        <summary>
          <span className="fold-title">Record</span>
          <span className="fold-meta">JSON</span>
        </summary>
        <div className="fold-body">
          <pre className="source">{JSON.stringify(submission, null, 2)}</pre>
        </div>
      </details>
    </>
  );
}

const DONE: Record<string, string> = {
  accept: "Recommendation accepted. Logged in the audit trail.",
  override: "Override saved. Logged in the audit trail with your note.",
  assign: "Case assigned to you.",
  rfi: "Request marked as sent.",
};

const STATUS_HELP: Record<string, string> = {
  New: "Nobody has acted on this case yet.",
  "In review": "An analyst owns this case and is working on it.",
  "Escalated / MLRO": "Sent to the money laundering reporting officer (MLRO) to decide.",
  Decided: "An analyst has accepted or overridden the recommendation.",
};

type Email = { label: string; to: string; subject: string; body: string };

function EmailDraft({ label, to, subject, body }: Email) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(timer.current), []);

  async function copy() {
    try {
      await navigator.clipboard.writeText(`Subject: ${subject}\n\n${body}`);
      setCopyError(false);
      setCopied(true);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopyError(true);
    }
  }

  return (
    <>
      <button
        type="button"
        title="Show a draft email you can copy or open in your mail app. Nothing is sent."
        onClick={() => dialog.current?.showModal()}
      >
        {label}
      </button>
      <dialog
        ref={dialog}
        className="email-dialog"
        aria-labelledby="email-dialog-title"
        onClose={() => setCopied(false)}
      >
        <h2 id="email-dialog-title">{label}</h2>
        <dl className="facts ruled">
          <dt>To</dt>
          <dd>{to || "The customer's email address (add it in your mail app)"}</dd>
          <dt>Subject</dt>
          <dd>{subject}</dd>
        </dl>
        <label htmlFor="email-dialog-body" className="email-label">
          Body
        </label>
        <textarea id="email-dialog-body" readOnly rows={12} value={body} />
        {copyError ? (
          <p className="email-error" role="alert">
            Copy did not work in this browser. Select the text and copy it by hand.
          </p>
        ) : null}
        <div className="toolbar email-actions">
          <button
            type="button"
            className="primary"
            autoFocus
            onClick={() => {
              void copy();
            }}
          >
            {copied ? "Copied" : "Copy email"}
          </button>
          <a className="button-link" href={mailto(to, subject, body)}>
            Open in mail app
          </a>
          <button type="button" onClick={() => dialog.current?.close()}>
            Close
          </button>
          <span className="email-live" aria-live="polite">
            {copied ? "Email copied" : ""}
          </span>
        </div>
      </dialog>
    </>
  );
}

function crossCheckSummary(data: CaseDetail) {
  if (!data.risk || !data.decision) return "No estimate";
  const ranked: [string, number][] = [
    ["CLOSE", data.risk.pClose],
    ["RFI", data.risk.pRfi],
    ["ESCALATE", data.risk.pEscalate],
  ];
  const top = ranked.reduce((left, right) => (right[1] > left[1] ? right : left));
  return top[0] === data.decision.verdict ? "Model agrees" : "Model differs, take a second look";
}

function AnalystDecision({ data, done }: { data: CaseDetail; done: string }) {
  const status = data.work.status || "New";
  const last = data.trail.find(
    (event) => event.kind === "human" && (event.action === "accept" || event.action === "override"),
  );
  return (
    <div className="analyst-block" role="status">
      {done ? <p className="done">{done}</p> : null}
      <dl className="facts ruled">
        <dt>Analyst decision</dt>
        <dd>
          {last ? (
            <>
              <strong>{verdictLabel(data.work.decidedVerdict)}</strong>
              {last.action === "override" ? " (overridden)" : " (recommendation accepted)"} by{" "}
              {last.actor}, {when(last.at)}
            </>
          ) : (
            "Not decided yet"
          )}
        </dd>
        <dt>Status</dt>
        <dd>
          <span className="hint" title={STATUS_HELP[status]}>
            {status}
          </span>
          {data.work.assignee ? ` · owner ${data.work.assignee}` : " · no owner"}
          {data.work.rfiSent ? " · request sent" : ""}
        </dd>
      </dl>
    </div>
  );
}

function plural(count: number, noun: string): string {
  return `${count.toLocaleString("en-GB")} ${noun}${count === 1 ? "" : "s"}`;
}

function withoutTitle(text: string, title: string): string {
  const [first, ...rest] = text.split("\n");
  return first.replace(/^#\s+/, "").trim() === title.trim() ? rest.join("\n").trimStart() : text;
}
