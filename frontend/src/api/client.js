// Reasoning service client (port 8002). The engine (port 8001) is reached
// *through* the reasoning service's /cases proxy, so integration day is a
// backend env-var change and this file never moves.
const BASE = import.meta.env.VITE_REASONING_URL || "http://localhost:8002";

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail || detail;
    } catch { /* not json */ }
    throw new Error(detail);
  }
  return res.json();
}

export const api = {
  health: () => req("/health"),
  listCases: (threshold) =>
    req(`/cases${threshold != null ? `?threshold=${threshold}` : ""}`),
  getCase: (id) => req(`/cases/${id}`),
  evidence: (id) => req(`/evidence/${id}`, { method: "POST" }),
  investigate: (id) => req(`/investigate/${id}`, { method: "POST" }),
  fullInvestigation: (id) => req(`/investigate/${id}/full`),
  searchRegulations: (q, k = 3) =>
    req(`/regulations/search?q=${encodeURIComponent(q)}&k=${k}`),
  exportStr: (id, draft, actor = "analyst") =>
    req(`/export/${id}?actor=${encodeURIComponent(actor)}`, {
      method: "POST",
      body: JSON.stringify(draft),
    }),
  validateGrammar: (raw) =>
    req("/grammar/validate", { method: "POST", body: JSON.stringify({ raw }) }),
  strSchema: () => req("/schema/str"),
  auditForCase: (id) => req(`/audit/${id}`),
  auditVerify: () => req("/audit/verify"),
};

export function formatINR(amount) {
  return "₹" + Number(amount).toLocaleString("en-IN", { maximumFractionDigits: 0 });
}

export const BAND_STYLE = {
  RED: { color: "var(--status-critical)", label: "RED", icon: "▲" },
  YELLOW: { color: "var(--status-warning)", label: "YELLOW", icon: "◆" },
  GREEN: { color: "var(--status-good)", label: "GREEN", icon: "●" },
};

export const CONF_STYLE = {
  red: { color: "var(--status-critical)", label: "verify", icon: "▲" },
  yellow: { color: "var(--status-warning)", label: "review", icon: "◆" },
  green: { color: "var(--status-good)", label: "confident", icon: "●" },
};
