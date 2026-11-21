import type { Verdict } from "../types";

const VERDICT_SHORT: Record<string, string> = {
  CLOSE: "CLOSE",
  RFI: "REQUEST INFO",
  ESCALATE: "ESCALATE",
};

export function VerdictPill({ verdict }: { verdict: Verdict }) {
  if (!verdict) return <span>—</span>;
  const tone = verdict === "CLOSE" ? "close" : verdict === "RFI" ? "rfi" : "escalate";
  return <span className={`tag ${tone}`}>{VERDICT_SHORT[verdict] ?? verdict}</span>;
}
