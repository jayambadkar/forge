import { Link } from "react-router-dom";
import { labelFor, percent, reasonLabel, sentences, verdictLabel, when } from "../format";
import type { AuditEvent } from "../types";
import { VerdictPill } from "./Verdict";

const WHO: Record<string, string> = {
  ai: "Forge policy engine",
  model: "Model cross-check",
  system: "Batch job",
};

function headline(event: AuditEvent) {
  switch (event.action) {
    case "policy":
      return "Recommended";
    case "accept":
      return "Accepted the recommendation";
    case "override":
      return "Overrode the recommendation";
    case "assign":
      return "Took the case";
    case "rfi":
      return "Sent the request for information";
    case "second-check":
      return "Model cross-check points elsewhere";
    case "batch":
      return "Ran the batch";
    default:
      return event.action;
  }
}

// "status=New; verdict=—; assignee=—; rfiSent=False" into named fields.
function fields(value: string | undefined) {
  const found: Record<string, string> = {};
  for (const part of (value || "").split(";")) {
    const [key, ...rest] = part.split("=");
    if (key?.trim()) found[key.trim()] = rest.join("=").trim();
  }
  return found;
}

function changes(before: string | undefined, after: string | undefined) {
  const left = fields(before);
  const right = fields(after);
  const names: Record<string, string> = {
    status: "Status",
    verdict: "Decision",
    assignee: "Owner",
    rfiSent: "Request sent",
  };
  return Object.keys(names)
    .filter((key) => left[key] !== right[key])
    .map((key) => {
      const show = (value: string | undefined) =>
        key === "verdict" ? verdictLabel(value === "—" ? "" : value) : value || "—";
      return { name: names[key], from: show(left[key]), to: show(right[key]) };
    });
}

function reviewer(llm: string | undefined) {
  if (!llm || llm === "not-used") return "Not used (switched off)";
  return llm;
}

export function AuditEntry({ event, showCase = false }: { event: AuditEvent; showCase?: boolean }) {
  const who = WHO[event.kind] ?? event.actor;
  const diff = changes(event.before, event.after);
  const why = event.kind === "ai" ? sentences(event.reason) : [];
  return (
    <li className={`audit-entry ${event.kind}`}>
      <div className="audit-head">
        <span className="nums">{when(event.at)}</span>
        <strong>{who}</strong>
        {event.kind === "human" ? <span>{event.actor}</span> : null}
        {showCase && event.caseId ? (
          <Link to={`/cases/${event.institution}/${event.caseId}`} className="nums">
            {event.caseId}
          </Link>
        ) : null}
        {showCase && event.institution ? <span>{labelFor(event.institution)}</span> : null}
      </div>
      <p className="audit-title">
        {headline(event)}
        {event.verdict && event.action !== "assign" && event.action !== "batch" ? (
          <>
            {" "}
            <VerdictPill verdict={event.verdict as "CLOSE" | "RFI" | "ESCALATE"} />
          </>
        ) : null}
        {event.kind === "ai" && event.reasonCode ? ` ${reasonLabel(event.reasonCode)}` : ""}
      </p>
      {event.kind === "ai" ? (
        <dl className="facts">
          <dt>Decided by</dt>
          <dd>Written policy rules, version {event.model || "—"}</dd>
          <dt>Rules triggered</dt>
          <dd className="nums">{event.rules?.length ? event.rules.join(", ") : "—"}</dd>
          <dt>Reason code</dt>
          <dd className="nums">{event.reasonCode || "—"}</dd>
          <dt>Evidence used</dt>
          <dd>
            {event.evidence?.length ? (
              <span className="chips">
                {event.evidence.map((id) => (
                  <code key={id}>{id}</code>
                ))}
              </span>
            ) : (
              "None"
            )}
          </dd>
          <dt>Model cross-check</dt>
          <dd>
            {event.confidence !== undefined
              ? `Gives this outcome ${percent(event.confidence)}`
              : "—"}
          </dd>
          <dt>Language-model reviewer</dt>
          <dd>{reviewer(event.llm)}</dd>
          <dt>Run</dt>
          <dd className="nums">{event.jobId || "—"}</dd>
        </dl>
      ) : null}
      {why.length ? (
        <details className="why">
          <summary>Reasoning ({why.length} steps)</summary>
          <ol>
            {why.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ol>
        </details>
      ) : null}
      {event.kind === "model" ? (
        <dl className="facts">
          <dt>Model expects</dt>
          <dd>{verdictLabel(event.verdict)}</dd>
          <dt>Effect</dt>
          <dd>None. The recommendation stands; an analyst should take a second look.</dd>
        </dl>
      ) : null}
      {event.kind === "human" && diff.length ? (
        <dl className="facts">
          {diff.map((item) => (
            <div key={item.name} className="fact-pair">
              <dt>{item.name}</dt>
              <dd>
                {item.from} → <strong>{item.to}</strong>
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
      {event.note ? (
        <p className="audit-note">
          <strong>Note:</strong> {event.note}
        </p>
      ) : null}
      {event.kind === "system" ? <p className="audit-note">{event.detail}</p> : null}
    </li>
  );
}
