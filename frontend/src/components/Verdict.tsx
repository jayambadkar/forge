import type { Verdict } from "../types";

export function VerdictPill({ verdict }: { verdict: Verdict }) {
  if (!verdict) return <span>—</span>;
  const tone = verdict === "CLOSE" ? "close" : verdict === "RFI" ? "rfi" : "escalate";
  return <span className={`tag ${tone}`}>{verdict}</span>;
}
