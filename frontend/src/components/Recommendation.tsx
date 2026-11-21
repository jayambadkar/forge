import { gbp, percent, reasonLabel, sentences, verdictLabel } from "../format";
import type { CaseDetail } from "../types";
import { VerdictPill } from "./Verdict";

type Props = { data: CaseDetail; amount: number };

export function Recommendation({ data, amount }: Props) {
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
      <dl className="facts">
        <dt>Rules triggered</dt>
        <dd>
          {data.alerts.map((alert) => (
            <span key={alert.id} className="rule">
              <code>{alert.ruleId}</code> {alert.ruleName}
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
                <code key={id} title={docs.get(id)?.title}>
                  {id} · {docs.get(id)?.kind.replaceAll("_", " ")}
                </code>
              ))}
            </span>
          ) : (
            "None. No document on file explains the activity."
          )}
        </dd>
        <dt>Other records used</dt>
        <dd>
          {[
            usedAlerts.length
              ? `${usedAlerts.length} alert${usedAlerts.length === 1 ? "" : "s"}`
              : "",
            usedTxns.length
              ? `${usedTxns.length} transaction${usedTxns.length === 1 ? "" : "s"}`
              : "",
            ...other,
          ]
            .filter(Boolean)
            .join(" · ") || "—"}
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
      <p>
        A separate machine-learning model reads the same case facts and estimates how likely each
        outcome is. It was trained on Forge's past decisions across all four firms. It never changes
        the recommendation; it flags cases worth a second look.
      </p>
      <div className={agrees ? "callout agree" : "callout differ"} role="status">
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
