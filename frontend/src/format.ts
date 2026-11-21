export function gbp(amount: number | null | undefined) {
  if (amount === null || amount === undefined) return "—";
  return new Intl.NumberFormat("en-GB", { style: "currency", currency: "GBP" }).format(amount);
}

export function when(value: string) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 16);
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function ageDays(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 0;
  return Math.max(0, Math.floor((Date.now() - date.getTime()) / 86400000));
}

export function openedOn(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value.slice(0, 10) || "—";
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(date);
}

export function openLabel(value: string) {
  if (!value) return "Open date not recorded";
  return `Opened ${openedOn(value)} · ${sla(ageDays(value))}`;
}

export function sla(days: number) {
  if (days <= 0) return "Opened today";
  if (days === 1) return "1 day open";
  return `${days.toLocaleString("en-GB")} days open`;
}

export function mailto(to: string, subject: string, body: string) {
  const address = to ? encodeURIComponent(to) : "";
  return `mailto:${address}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

export function labelFor(id: string) {
  return (
    {
      bank: "Retail bank",
      emoney: "E-money",
      investment: "Investment",
      payments_fx: "Payments & FX",
    }[id] ?? id
  );
}

export const VERDICT_LABEL: Record<string, string> = {
  CLOSE: "Close",
  RFI: "Request information",
  ESCALATE: "Escalate to MLRO",
};

export function verdictLabel(verdict: string | undefined) {
  return verdict ? (VERDICT_LABEL[verdict] ?? verdict) : "—";
}

const REASON_LABEL: Record<string, string> = {
  COLLECTION_DOCUMENTED: "Cash collection is documented",
  BUSINESS_RECORDS_RECONCILE: "Business records reconcile",
  DOCUMENTED_EVENT: "A documented life or business event",
  INVOICE_MATCHES: "Invoice or contract matches the payments",
  OWN_ACCOUNT: "Transfer between the customer's own accounts",
  GROUP_COMPANY: "Payment within the same group of companies",
  THIRD_PARTY_DOCUMENTED: "Third party is documented",
  REFUND_OF_EARLIER_PAYMENT: "Refund of an earlier payment",
  RETURNING_CUSTOMER: "Covered by an earlier review",
  LIST_MATCH_DIFFERENT_PARTY: "List match is a different person",
  WITHIN_PROFILE: "Within the declared profile",
  RFI_PURPOSE_DOCUMENTS: "Ask for documents showing the purpose",
  RFI_BUSINESS_RECORDS: "Ask for business records",
  RFI_SOURCE_OF_FUNDS: "Ask where the money came from",
  RFI_COUNTERPARTY_DETAILS: "Ask who the counterparty is",
  RFI_UPDATED_PROFILE: "Ask for an updated income or turnover",
  ESC_MULE_ACTIVITY: "Possible money mule activity",
  ESC_STRUCTURING: "Payments split to stay under a threshold",
  ESC_UNEXPLAINED_FUNDS: "Unexplained funds moved on",
  ESC_PASS_THROUGH: "Money passed straight through",
  ESC_INVOICE_MISMATCH: "Invoices do not support the payments",
  ESC_HIGH_RISK_CORRIDOR: "Undeclared higher-risk country",
  ESC_ACCOUNT_MISUSE: "Account used for another purpose",
  ESC_THIRD_PARTY_FUNDING: "Unexplained third-party funding",
  ESC_EARLY_REDEMPTION: "Funds bought and quickly sold back",
  ESC_LISTED_PARTY: "Confirmed match to the internal list",
};

export function reasonLabel(code: string | undefined) {
  if (!code) return "—";
  return REASON_LABEL[code] ?? code.replaceAll("_", " ").toLowerCase();
}

export function sentences(text: string | undefined) {
  return (text || "")
    .split(/(?<=[.!?])\s+(?=[A-Z£0-9])/)
    .map((part) => part.trim())
    .filter(Boolean);
}

export function percent(value: number) {
  return `${Math.round(value * 100)}%`;
}
