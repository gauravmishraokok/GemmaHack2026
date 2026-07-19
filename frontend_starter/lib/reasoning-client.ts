// Client for the viGEMMAlya reasoning service (:8002). Talks to a real,
// running backend — no mocked data. See v0_backend_spec.md at the repo root
// for the full contract this is built against.

const BASE = process.env.NEXT_PUBLIC_REASONING_URL || "http://localhost:8002";

async function req<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail ?? detail;
    } catch {
      /* not json */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
}

export type CaseSummary = {
  case_id: string;
  risk_band: "RED" | "YELLOW" | "GREEN";
  p: number;
  member_count: number;
};

export type HealthResponse = {
  status: string;
  service: string;
  case_source: string;
  mock_llm: boolean;
  llm: { ollama: string; model: string; model_available?: boolean };
  audit_chain: { intact: boolean; length: number };
};

export type RiskScore = { p: number; margin: number; ood: number };

export type Transaction = {
  txn_id: string;
  from_account: string;
  to_account: string;
  amount: number;
  currency: string;
  timestamp: string;
  typology_flag: string | null;
  xgb_score: number | null;
};

export type GraphEdge = {
  source: string;
  target: string;
  relation: "SENT" | "OWNED_BY" | "DIRECTOR_OF" | "LINKED_PAN";
  weight: number | null;
};

export type Entity = {
  id: string;
  type: "Account" | "Person" | "Company" | "PAN";
  name: string | null;
  owner_pan: string | null;
  director_of: string[] | null;
  kyc_status: "VERIFIED" | "PENDING" | "FAILED" | null;
  entity_subtype: string | null;
  jurisdiction: string | null;
  linked_company: string | null;
};

export type SharedPanGroup = { pan: string; accounts: string[] };
export type AlertDetail = { account: string; alert_type: string; detail: string };

export type Case = {
  case_id: string;
  risk: RiskScore;
  risk_band: "RED" | "YELLOW" | "GREEN";
  member_alert_ids: string[];
  accounts: string[];
  transactions: Transaction[];
  graph_edges: GraphEdge[];
  entities: Entity[];
  shared_pan_groups: SharedPanGroup[];
  alert_details: AlertDetail[];
};

export type EvidenceItem = { ev_id: string; kind: string; source_ref: string; value: string };
export type TimelineEvent = { ts: string; event: string };
export type Relationship = { type: string; entities: string[] };
export type RegulationRef = { section: string; text_snippet: string; relevance: string };

export type EvidencePack = {
  case_id: string;
  evidence: EvidenceItem[];
  timeline: TimelineEvent[];
  relationships: Relationship[];
  regulations: RegulationRef[];
  risk: RiskScore;
  missing_evidence: string[];
};

export type NarrationSentence = { sentence: string; confidence: number; band: "green" | "yellow" | "red" };

export type STRDraft = {
  case_id: string;
  gos_tag: string;
  narration: NarrationSentence[];
  recommended_action: string;
  amounts_cited: number[];
  evidence_refs: string[];
};

export type InvestigationResult = {
  case_id: string;
  investigation_summary: string;
  behaviour_pattern: string;
  suggested_questions: string[];
  str_draft: STRDraft | null;
  status: "OK" | "INSUFFICIENT_EVIDENCE";
};

export type Diagnostics = {
  model: string;
  logprobs_available: boolean;
  total_tokens: number;
  answer_tokens: number;
  overall_confidence: number;
  amount_violations: string[];
  evidence_assessment: { ev_id: string; observation: string }[];
  model_sufficiency: string | null;
  elapsed_s: number;
  gate?: string;
};

export type FullInvestigation = {
  result: InvestigationResult;
  evidence: EvidencePack;
  diagnostics: Diagnostics;
};

export type NotifyStatus = { status: "sent" | "failed" | "skipped"; to?: string; reason?: string; detail?: string };

export type ExportResponse = {
  xml: string;
  audit_entry: {
    seq: number;
    ts: string;
    actor: string;
    action: string;
    case_id: string;
    evidence_refs: string[];
    detail: Record<string, unknown>;
    prev_hash: string;
    hash: string;
  };
  notifications?: { email?: NotifyStatus; sms?: NotifyStatus };
};

export type AuditEntry = ExportResponse["audit_entry"];

export const reasoningApi = {
  base: BASE,
  health: () => req<HealthResponse>("/health"),
  listCases: (threshold?: number) =>
    req<CaseSummary[]>(`/cases${threshold != null ? `?threshold=${threshold}` : ""}`),
  getCase: (caseId: string) => req<Case>(`/cases/${caseId}`),
  evidence: (caseId: string) => req<EvidencePack>(`/evidence/${caseId}`, { method: "POST" }),
  investigate: (caseId: string) =>
    req<InvestigationResult>(`/investigate/${caseId}`, { method: "POST" }),
  fullInvestigation: (caseId: string) => req<FullInvestigation>(`/investigate/${caseId}/full`),
  searchRegulations: (q: string, k = 3) =>
    req<RegulationRef[]>(`/regulations/search?q=${encodeURIComponent(q)}&k=${k}`),
  exportStr: (caseId: string, draft: STRDraft, actor = "analyst") =>
    req<ExportResponse>(`/export/${caseId}?actor=${encodeURIComponent(actor)}`, {
      method: "POST",
      body: JSON.stringify(draft),
    }),
  validateGrammar: (raw: string) =>
    req<{ valid: boolean; error: string | null; checks_failed: string[] }>("/grammar/validate", {
      method: "POST",
      body: JSON.stringify({ raw }),
    }),
  strSchema: () =>
    req<{ schema: unknown; gos_tags: string[]; recommended_actions: string[] }>("/schema/str"),
  auditForCase: (caseId: string) => req<AuditEntry[]>(`/audit/${caseId}`),
  auditVerify: () => req<{ intact: boolean; length: number }>("/audit/verify"),
  recentEvents: (caseId?: string, limit = 50) =>
    req<PipelineEvent[]>(
      `/events/recent?limit=${limit}${caseId ? `&case_id=${encodeURIComponent(caseId)}` : ""}`
    ),
};

// Engine currencies are IBM-AML full names ("US Dollar", "Euro", "Rupee"),
// not ISO codes — map to symbols, fall back to the raw name.
const CURRENCY_SYMBOLS: Record<string, string> = {
  inr: "₹", rupee: "₹", "indian rupee": "₹",
  usd: "$", "us dollar": "$",
  eur: "€", euro: "€",
  gbp: "£", "uk pound": "£", pound: "£",
  yen: "¥", jpy: "¥",
};

export function formatAmount(amount: number, currency = ""): string {
  const sym = CURRENCY_SYMBOLS[currency.trim().toLowerCase()];
  if (sym === "₹") return "₹" + Number(amount).toLocaleString("en-IN", { maximumFractionDigits: 0 });
  const grouped = Number(amount).toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (sym) return sym + grouped;
  return currency ? `${grouped} ${currency}` : grouped;
}

export const BAND_STYLE: Record<string, { color: string; label: string; icon: string }> = {
  RED: { color: "var(--status-critical)", label: "RED", icon: "▲" },
  YELLOW: { color: "var(--status-warning)", label: "YELLOW", icon: "◆" },
  GREEN: { color: "var(--status-good)", label: "GREEN", icon: "●" },
};

export const CONF_STYLE: Record<string, { color: string; label: string; icon: string }> = {
  red: { color: "var(--status-critical)", label: "verify", icon: "▲" },
  yellow: { color: "var(--status-warning)", label: "review", icon: "◆" },
  green: { color: "var(--status-good)", label: "confident", icon: "●" },
};

export type PipelineEvent = {
  case_id: string;
  stage: string;
  status: "start" | "ok" | "fail" | "skip";
  detail: string;
  meta: Record<string, unknown>;
  ts: number;
};

export const STAGES = [
  "evidence_build",
  "evidence_gate",
  "gemma_reasoning",
  "model_gate",
  "grounding",
  "confidence",
  "complete",
  "export",
] as const;

export const STAGE_LABELS: Record<string, string> = {
  evidence_build: "Assembling evidence",
  evidence_gate: "Evidence gate",
  gemma_reasoning: "Gemma reasoning",
  model_gate: "Model self-assessment",
  grounding: "Grounding verification",
  confidence: "Confidence scoring",
  complete: "Complete",
  export: "Export & attest",
};

/**
 * Opens an SSE connection to the reasoning service's live pipeline feed.
 * Returns a cleanup function. Reconnects are handled by EventSource natively
 * on network blips; call the returned cleanup on unmount to close cleanly.
 */
export function subscribePipelineEvents(
  onEvent: (e: PipelineEvent) => void,
  onOpen?: () => void,
  onError?: () => void,
  caseId?: string
): () => void {
  const url = `${BASE}/events/stream${caseId ? `?case_id=${encodeURIComponent(caseId)}` : ""}`;
  const es = new EventSource(url);
  es.onopen = () => onOpen?.();
  es.onerror = () => onError?.();
  es.onmessage = (ev) => {
    if (!ev.data) return;
    try {
      const parsed = JSON.parse(ev.data) as PipelineEvent;
      onEvent(parsed);
    } catch {
      /* keepalive comment lines never reach onmessage */
    }
  };
  return () => es.close();
}
