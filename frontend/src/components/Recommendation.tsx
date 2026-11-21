import { gbp, percent, reasonLabel, sentences, verdictLabel } from "../format";
import type { CaseDetail } from "../types";
import { VerdictPill } from "./Verdict";

export type EvidenceRef = {
  kind: "doc" | "alert" | "txn" | "list" | "other";
  type: string;
  label: string;
};
export type DescribeEvidence = (id: string) => EvidenceRef | undefined;

/** Builds a lookup from evidence id to what it points at in this case. */
export function evidenceLookup(data: CaseDetail): DescribeEvidence {
  const found = new Map<string, EvidenceRef>();
  for (const doc of data.evidence)
    found.set(doc.id, {
      kind: "doc",
      type: doc.kind.replaceAll("_", " "),
      label: `${doc.kind.replaceAll("_", " ")}: ${doc.title || doc.id}`,
    });
  for (const alert of data.alerts)
    found.set(alert.id, {
      kind: "alert",
      type: `alert ${alert.ruleId}`,
      label: `${alert.ruleId} ${alert.ruleName}`,
    });
  for (const txn of data.timeline)
    found.set(txn.id, {
      kind: "txn",
      type: "transaction",
      label: `${txn.timestamp.slice(0, 10)} ${txn.counterparty || "No counterparty name"} ${gbp(txn.amount)}`,
    });
  return (id) =>
    found.get(id) ??
    (/-L\d+$/.test(id)
      ? { kind: "list", type: "internal list entry", label: "Internal list entry" }
      : undefined);
}

type ChipProps = {
  id: string;
  text?: string;
  describe?: DescribeEvidence;
  onSelect?: (id: string) => void;
};

/** One evidence id. A button that jumps to the record when the case is loaded. */
export function EvidenceChip({ id, text, describe, onSelect }: ChipProps) {
  const ref = describe?.(id);
  const title = ref?.label ?? id;
  const shown = text ?? (ref ? `${id} · ${ref.type}` : id);
  if (!onSelect || !ref || ref.kind === "list")
    return (
      <code className="chip" title={title}>
        {shown}
      </code>
    );
  const where = ref.kind === "doc" ? "Evidence" : ref.kind === "alert" ? "Alerts" : "Transactions";
  return (
    <button
      type="button"
      className="chip"
      title={`${title}. Show it in ${where}.`}
      onClick={() => onSelect(id)}
    >
      <code>{shown}</code>
    </button>
  );
}

type Props = { data: CaseDetail; amount: number; onSelect?: (id: string) => void };

export function Recommendation({ data, amount, onSelect }: Props) {
  const decision = data.decision;
  if (!decision) return <p>No recommendation has been written for this case.</p>;
  const tone = decision.verdict.toLowerCase();
  const docs = new Map(data.evidence.map((doc) => [doc.id, doc]));
  const alerts = new Set(data.alerts.map((alert) => alert.id));
  const txns = new Set(data.timeline.map((txn) => txn.id));
  const usedDocs = decision.evidence.filter((id) => docs.has(id));
  const usedAlerts = decision.evidence.filter((id) => alerts.has(id));
  const usedTxns = decision.evidence.filter((id) => txns.has(id));
  const other = decision.evidence.filter((id) => !docs.has(id) && !alerts.has(id) && !txns.has(id));
  const steps = sentences(decision.reason);
  const describe = evidenceLookup(data);
  return (
    <section className={`decision ${tone}`} aria-label="Recommendation">
      <div className="decision-head">
        <VerdictPill verdict={decision.verdict} />
        <div>
          <p className="decision-title">{verdictLabel(decision.verdict)}</p>
          <p className="decision-code">
            {reasonLabel(decision.reasonCode)} · <code>{decision.reasonCode}</code>
          </p>
        </div>
      </div>
      <dl className="facts ruled">
        <dt>Rules triggered</dt>
        <dd>
          {data.alerts.map((alert) => (
            <span key={alert.id} className="rule">
              <code>{alert.ruleId}</code>
              <span>{alert.ruleName}</span>
            </span>
          ))}
        </dd>
        <dt>Amount on the alerts</dt>
        <dd className="nums">{gbp(amount)}</dd>
        <dt>Documents relied on</dt>
        <dd>
          {usedDocs.length ? (
            <span className="chips">
              {usedDocs.map((id) => (
                <EvidenceChip
                  key={id}
                  id={id}
                  text={`${id} · ${docs.get(id)?.kind.replaceAll("_", " ") ?? ""}`}
                  describe={describe}
                  onSelect={onSelect}
                />
              ))}
            </span>
          ) : (
            "None. No document on file explains the activity."
          )}
        </dd>
        <dt>Other records used</dt>
        <dd>
          {usedAlerts.length || usedTxns.length || other.length ? (
            <span className="chips">
              {[...usedAlerts, ...usedTxns, ...other].map((id) => (
                <EvidenceChip key={id} id={id} describe={describe} onSelect={onSelect} />
              ))}
            </span>
          ) : (
            "—"
          )}
        </dd>
      </dl>
      <h2 className="decision-sub">Why</h2>
      <ol className="steps">
        {steps.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ol>
    </section>
  );
}

export function CrossCheck({ data }: { data: CaseDetail }) {
  const risk = data.risk;
  const decision = data.decision;
  if (!risk || !decision) return <p>No model estimate is stored for this case.</p>;
  const ranked = [
    { verdict: "CLOSE", value: risk.pClose },
    { verdict: "RFI", value: risk.pRfi },
    { verdict: "ESCALATE", value: risk.pEscalate },
  ];
  const top = ranked.reduce((left, right) => (right.value > left.value ? right : left));
  const agrees = top.verdict === decision.verdict;
  return (
    <>
      <div
        className={agrees ? "callout agree" : "callout differ"}
        role="status"
        title="A separate model trained on Forge's past decisions estimates each outcome from the case facts. It never changes the recommendation."
      >
        {agrees ? (
          <>
            <strong>Model agrees.</strong> It also points to{" "}
            {verdictLabel(top.verdict).toLowerCase()}, at {percent(top.value)}.
          </>
        ) : (
          <>
            <strong>Model differs. Take a second look.</strong> It points to{" "}
            {verdictLabel(top.verdict).toLowerCase()} at {percent(top.value)}, while the
            recommendation is {verdictLabel(decision.verdict).toLowerCase()}.
          </>
        )}
      </div>
      <dl className="bars">
        {ranked.map((item) => (
          <div key={item.verdict} className="bar-row">
            <dt>{verdictLabel(item.verdict)}</dt>
            <dd>
              <span className={`bar ${item.verdict.toLowerCase()}`}>
                <i style={{ width: `${Math.max(1, item.value * 100)}%` }} />
              </span>
              <span className="nums">{percent(item.value)}</span>
            </dd>
          </div>
        ))}
      </dl>
    </>
  );
}
