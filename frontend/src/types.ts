export type Verdict = "CLOSE" | "RFI" | "ESCALATE" | "";

export type ReasonCount = { code: string; count: number };

export type Institution = {
  id: string;
  label: string;
  book: string;
  cases: number;
  close: number;
  rfi: number;
  escalate: number;
  reasons: ReasonCount[];
};

export type CaseSummary = {
  caseId: string;
  institution: string;
  customerId: string;
  customerName: string;
  verdict: Verdict;
  reasonCode: string;
  reason: string;
  amount: number | null;
  alertCount: number;
  openedAt: string;
  rules: string;
  slaDays: number;
  pClose: number;
  pRfi: number;
  pEscalate: number;
  riskBand: string;
  status: string;
  assignee: string;
  rfiSent: boolean;
  decidedVerdict: string;
};

export type CasePage = { total: number; cases: CaseSummary[] };

export type Txn = {
  id: string;
  timestamp: string;
  amount: number;
  currency: string;
  direction: string;
  channel: string;
  counterparty: string;
  country: string;
  reference: string;
  inAlert: boolean;
};

export type EvidenceDoc = {
  id: string;
  title: string;
  kind: string;
  dated: string;
  text: string;
  cited: boolean;
};

export type AuditEvent = {
  id: string;
  at: string;
  kind: string;
  actor: string;
  action: string;
  institution: string;
  caseId: string;
  detail: string;
  agent?: string;
  model?: string;
  mlModel?: string;
  mlScore?: number;
  llm?: string;
  jobId?: string;
  verdict?: string;
  reasonCode?: string;
  reason?: string;
  evidence?: string[];
  rules?: string[];
  confidence?: number;
  before?: string;
  after?: string;
  note?: string;
};

export type RelatedCase = {
  institution: string;
  caseId: string;
  customerName: string;
  verdict: Verdict;
  link: string;
  via: string;
};

export type CaseWork = {
  status: string;
  assignee: string;
  rfiSent: boolean;
  decidedVerdict: string;
  note: string;
  updatedAt: string;
};

export type CaseDetail = {
  caseId: string;
  institution: string;
  openedAt: string;
  heldPaymentId: string;
  customer: {
    id: string;
    name: string;
    kind: string;
    dob: string;
    occupation: string;
    risk: string;
    expectedMonthly: number | null;
  };
  alerts: {
    id: string;
    ruleId: string;
    ruleName: string;
    message: string;
    transactionIds: string[];
  }[];
  timeline: Txn[];
  evidence: EvidenceDoc[];
  reviews: { id: string; date: string; ruleId: string; verdict: string; text: string }[];
  decision: { verdict: Verdict; reasonCode: string; reason: string; evidence: string[] } | null;
  risk: { pClose: number; pRfi: number; pEscalate: number; groups?: Record<string, number> } | null;
  work: CaseWork;
  trail: AuditEvent[];
  related: RelatedCase[];
};

export type DashboardStats = {
  cases: number;
  open: number;
  close: number;
  rfi: number;
  escalate: number;
  decided: number;
  inReview: number;
  new: number;
  escalated: number;
  ageing: number;
  wrongfulCloseRisk: number;
  sla0: number;
  sla1: number;
  sla2: number;
  sla3: number;
  syncedAt: string;
};

export type RunEvent = {
  kind: "status" | "log" | "case" | "done" | "error";
  text?: string;
  caseId?: string;
  verdict?: Verdict;
  reasonCode?: string;
  reason?: string;
};

export type Job = {
  id: string;
  institution: string;
  mode: string;
  startedAt: string;
  finishedAt: string;
  status: string;
  cases: number;
};
