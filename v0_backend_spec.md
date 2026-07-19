# viGEMMAlya — Backend API Specification (for v0 frontend generation)

This document is the complete, standalone contract for building a new frontend
against the viGEMMAlya backend. It covers **both services** — the Engine
(static/batch plane, port **8001**) and the Reasoning service (dynamic/interactive
plane, port **8002**) — because a v0 frontend talks to both.

Everything in this document is taken from the **live, running OpenAPI schema**
and **real captured responses**, not written from memory — every example payload
below is a genuine response from the system, not a fabricated sample. Treat this
as the source of truth; it is more precise than either service's own `/docs`
Swagger UI because it also explains *why* each field exists and what a frontend
should do with it.

---

## 0. How the two services relate (read this first)

```
┌─────────────────────────┐        ┌──────────────────────────────┐
│  ENGINE   (port 8001)    │        │  REASONING   (port 8002)      │
│  "static / batch plane"  │───────▶│  "dynamic / interactive plane"│
│                          │  HTTP  │                                │
│  - owns case generation  │        │  - proxies /cases from engine  │
│  - risk scoring (ML)     │        │  - builds evidence packs       │
│  - graph clustering      │        │  - runs Gemma investigations   │
│  - the source of truth   │        │  - drafts + exports STRs       │
│    for what a "Case" is  │        │  - audit log                   │
└─────────────────────────┘        └──────────────────────────────┘
```

**For a v0 frontend, talk to the Reasoning service (port 8002) for almost
everything.** It re-exposes the engine's case data under its own `/cases`
endpoints (proxying to the engine internally) *and* adds all the
investigation/evidence/STR/export functionality on top. You do not need to call
the Engine service (port 8001) directly for a normal user flow — it exists
mainly for two extra things: the `/risk/threshold` slider and the
`/metrics/comparison` chart (both described in §2 below; a v0 frontend may call
these on 8001 directly, or they can be proxied — see note in §2).

**Default local URLs:**
- Engine: `http://localhost:8001`
- Reasoning: `http://localhost:8002`

Both are plain REST/JSON, CORS-open (`*`) for local development. No
authentication is implemented (hackathon prototype — do not assume any auth
header is required or supported).

---

## 1. Data model — the shapes every response is built from

These are the exact Pydantic models both services validate against (`shared_contracts.py`,
frozen and identical on both sides). Every API response described later is
composed of these types. Read this section once, refer back to it constantly.

### `RiskScore`
```ts
type RiskScore = {
  p: number;      // 0.0–1.0 — probability this case is money-laundering-related
  margin: number;  // 0.0–1.0 — |p - 0.5| * 2, i.e. how far p is from the undecided midpoint
  ood: number;     // Mahalanobis distance from the training centroid; HIGHER = less reliable prediction (out-of-distribution)
}
```
**UI implication:** `p` drives the risk badge/color. `margin` can be shown as a
secondary "confidence in this score" bar. `ood` should be surfaced as a small
warning icon/tooltip when unusually high (e.g. > 10) — it means "this case
doesn't look like anything the model was trained on, treat the score with more
caution." Real observed `ood` values in this system range from ~0.9 to ~13.7.

### `Transaction`
```ts
type Transaction = {
  txn_id: string;               // e.g. "CASE-000006-TXN-0014920" — globally unique, case-prefixed
  from_account: string;         // account id, e.g. "80CAE3930"
  to_account: string;
  amount: number;               // the exact ledger amount, e.g. 4389.01 — NEVER round for grounding checks, only for display
  currency: string;             // FULL NAME, not ISO code: "US Dollar", "Euro", "UK Pound", "Rupee", "Yuan", "Canadian Dollar", "Swiss Franc", "Ruble", "Brazil Real", "Australian Dollar" all appear in real data. Default "INR" if absent.
  timestamp: string;            // ISO-8601, e.g. "2022-09-01T11:05:00" (naive, no timezone)
  typology_flag: string | null;  // null on most rows; when present: "structuring" | "smurfing" | "layering" | "round_tripping" | "funnel" (lowercase)
  xgb_score: number | null;      // 0.0–1.0 per-transaction ML anomaly score from the engine's XGBoost model; null if unavailable
}
```
**UI implication:** `currency` MUST be handled generically — do not hardcode ₹
formatting. See §6 "Currency formatting" for the exact symbol map this system
uses. `typology_flag` should render as a small colored chip on the transaction
row/timeline event when non-null. `xgb_score` can be shown as a secondary
"anomaly score" bar or tooltip per transaction.

### `GraphEdge`
```ts
type GraphEdge = {
  source: string;
  target: string;
  relation: "SENT" | "OWNED_BY" | "DIRECTOR_OF" | "LINKED_PAN";
  weight: number | null;
}
```
**UI implication (for a relationship graph view):** In practice, only `SENT`
(one edge per transaction, or aggregated per account-pair) and `LINKED_PAN`
(account → PAN node) are ever actually produced by this system today.
`OWNED_BY`/`DIRECTOR_OF` are valid per the schema but the current identity
pipeline never emits them — design the graph renderer to support all four
relation types (different edge style per type: solid for SENT, dashed for
LINKED_PAN, dotted for OWNED_BY, long-dash for DIRECTOR_OF) but don't be
surprised if only two ever appear in real data.

### `Entity`
```ts
type Entity = {
  id: string;                     // matches an account id, PAN node id ("PAN-XXXXX"), or person/company id
  type: "Account" | "Person" | "Company" | "PAN";   // CLOSED enum — exactly these 4 values, nothing else
  name: string | null;
  owner_pan: string | null;       // the PAN string this account is registered under (not prefixed with "PAN-")
  director_of: string[] | null;   // list of company entity ids this person directs (currently always null/empty in practice)
  kyc_status: "VERIFIED" | "PENDING" | "FAILED" | null;
  entity_subtype: string | null;  // free string: "Individual" | "Registered Business" | "Shell Company"
  jurisdiction: string | null;    // free string: "Standard" | "High Risk"
  linked_company: string | null;  // shell/shared company name, e.g. "Aurora Ventures Pvt Ltd"
}
```
**UI implication:** `kyc_status="FAILED"` + `entity_subtype="Shell Company"` +
`jurisdiction="High Risk"` together are the strongest visual "red flag" combo —
render this distinctly (e.g. a red outline or badge cluster) wherever an entity
card/node is shown. `type` is always one of exactly 4 values — never render a
"Shell Company" as if it were a `type`; it's a `type="Account"` with
`entity_subtype="Shell Company"`.

### `SharedPanGroup`
```ts
type SharedPanGroup = {
  pan: string;          // e.g. "TUOTE8885C"
  accounts: string[];   // >=2 account ids controlled by this one PAN — the "one beneficial owner, many accounts" evidence
}
```
**UI implication:** This is the single strongest piece of evidence in the whole
system — "N accounts are secretly the same person/entity." Give it prominent,
distinct visual treatment (e.g. a highlighted card at the top of an evidence
list, or a special node-grouping/halo in the graph view).

### `AlertDetail`
```ts
type AlertDetail = {
  account: string;
  alert_type: "velocity" | "threshold" | "structuring";
  detail: string;   // pre-formatted human-readable string, e.g. "velocity rule on 80C93DF00: 13 outbound transactions within a 48h window totalling 186,987,444"
}
```
**UI implication:** Render `detail` directly as-is — it's already a complete,
formatted sentence-fragment intended for display. Icon per `alert_type` is a
nice touch (a clock for velocity, a ceiling/gauge for threshold, a
split-arrows icon for structuring).

### `Case` — the central object
```ts
type Case = {
  case_id: string;                       // e.g. "CASE-000006"
  risk: RiskScore;
  risk_band: "RED" | "YELLOW" | "GREEN";
  member_alert_ids: string[];             // ids of the raw rule-engine alerts that fed into this case (often empty [] for ML-only-flagged cases)
  accounts: string[];                     // every account id involved in this case
  transactions: Transaction[];
  graph_edges: GraphEdge[];
  entities: Entity[];                     // one entity per account, plus PAN nodes
  shared_pan_groups: SharedPanGroup[];    // often [] — only present when >=2 accounts in THIS case share a PAN
  alert_details: AlertDetail[];           // often [] — only present when the rule engine actually fired on an account in this case
}
```
**Important real-world note:** `shared_pan_groups` and `alert_details` are
frequently **empty arrays**, even on RED-band cases — a case can be flagged
purely by repeated high ML anomaly scores with no rule-engine hit and no PAN
ring. Design the evidence UI to handle "no relationship evidence, no rule
alerts, purely ML-scored" gracefully (see the `CASE-000117` example in §5.2 —
a real RED case with `shared_pan_groups: []`, `alert_details: []`, and 8
transactions, which correctly fails the evidence-sufficiency check when
investigated).

### `CaseSummary` — the lightweight list-view shape
```ts
type CaseSummary = {
  case_id: string;
  risk_band: "RED" | "YELLOW" | "GREEN";
  p: number;
  member_count: number;   // often 0 for ML-only-flagged cases — do not assume >0
}
```

---

## 2. Engine API (port 8001) — reference only; a v0 frontend usually doesn't call this directly

| Method | Path | Purpose | Response |
|---|---|---|---|
| GET | `/health` | Liveness check | `{"status": "ok"}` |
| GET | `/cases?risk_band=RED&limit=50&offset=0` | Paginated case list. `limit` max 500, default 50. `risk_band` optional filter. | `CaseSummary[]` |
| GET | `/cases/{case_id}` | Full case object | `Case` |
| GET | `/cases/{case_id}/graph` | Same data, graph-shaped | `{"entities": Entity[], "edges": GraphEdge[]}` |
| POST | `/risk/threshold` | Recompute all case risk bands with a new RED cutoff. Body: `{"threshold": 0.6}` (default 0.6). `YELLOW = threshold - 0.3`, floored at 0.05; else GREEN. **This mutates the database** — every case's `risk_band` is recomputed and persisted. | `{"red": number, "yellow": number, "green": number}` — new counts |
| GET | `/metrics/comparison` | Model comparison chart data (frozen 4-field shape) | `ComparisonMetric[]` — see §2.1 |
| GET | `/metrics/comparison/full` | Same, plus AUPRC/AUROC | extended objects, not contract-frozen |

**A v0 frontend should call `/risk/threshold` and the two `/metrics/comparison*`
endpoints directly on port 8001** if building a "model comparison" or
"threshold tuning" admin view — the Reasoning service does not proxy these two.
Everything else (case browsing, investigation) should go through the Reasoning
service on port 8002, described in full below.

### 2.1 `ComparisonMetric` (real captured response from `/metrics/comparison/full`)
```json
[
  {"model":"gemma_probe","precision":0.925,"recall":0.74,"threshold":0.5196,"auprc":0.9029,"auroc":0.9048},
  {"model":"xgboost","precision":0.7596,"recall":0.79,"threshold":0.9203,"auprc":0.8574,"auroc":0.8793},
  {"model":"rule_count","precision":0.4098,"recall":1.0,"threshold":0.0,"auprc":0.4285,"auroc":0.3773}
]
```
**UI implication:** this is exactly 3 rows, always these 3 `model` values
(`gemma_probe`, `xgboost`, `rule_count`), suitable for a horizontal bar chart or
grouped bar chart comparing precision/recall/auprc/auroc across the three
detection approaches — this is meant to visually demonstrate "the learned model
beats the naive baseline."

**⚠️ Important caveat to caption honestly if displayed:** `gemma_probe` in this
comparison currently reflects a **TF-IDF text-vectorizer fallback**, not real
Gemma hidden-state activations, on the last local seed run (`USE_GEMMA=0` was
used for speed/reliability). If a "which model is this?" tooltip is shown,
don't claim it's Gemma unless you've confirmed the specific run used
`USE_GEMMA=1`.

---

## 3. Reasoning API (port 8002) — the main surface for a v0 frontend

### 3.1 `GET /health`

Real captured response:
```json
{
  "status": "ok",
  "service": "reasoning",
  "case_source": "engine",
  "mock_llm": false,
  "llm": {
    "ollama": "up",
    "model": "gemma4-sentinel",
    "model_available": true,
    "embed_model_available": true
  },
  "audit_chain": { "intact": true, "length": 34 }
}
```
**UI implication:** Poll this on app load (and optionally on an interval) to
drive a small status indicator in the header/nav: green dot if
`llm.ollama === "up"`, red/gray if `"down"` or `"mock"`. `case_source` tells you
whether cases are coming from the live engine (`"engine"`) or from bundled
offline fixtures (`"fixtures"`) — worth a small badge, e.g. "Live" vs "Demo
data", since it changes user expectations about case freshness.
`audit_chain.intact` should be `true`; if `false`, show a prominent tamper
warning somewhere (an audit/compliance page, if built).

---

### 3.2 `GET /cases?threshold=0.7`

List all cases (proxied from the engine). Query param `threshold` (0–1,
optional) recomputes risk bands **client-side in the reasoning service only**
when talking to fixture data — it does not mutate anything server-side and is
independent from the engine's `/risk/threshold` endpoint above.

**Real captured response** (truncated to first 3 of ~50+ real rows):
```json
[
  {"case_id":"CASE-000036","risk_band":"RED","p":0.9347,"member_count":1},
  {"case_id":"CASE-000117","risk_band":"RED","p":0.9286,"member_count":0},
  {"case_id":"CASE-000006","risk_band":"RED","p":0.9281,"member_count":5}
]
```

**UI implication — this is your case list / dashboard table.** Sort by `p`
descending by default (highest risk first). Group/filter by `risk_band` for a
tabbed or filtered dashboard view (RED / YELLOW / GREEN tabs, or a segmented
control). `member_count` can be a small "N alerts" chip but expect it to be 0
often — don't build a view that looks broken when it's 0.

---

### 3.3 `GET /cases/{case_id}`

Full `Case` object (schema in §1). Returns 404 if the case doesn't exist.

**Real captured response** — a small, complete real example (`CASE-000117`),
shown in full because it's short enough to read end-to-end and demonstrates
several important real-world shapes (multi-currency, empty `shared_pan_groups`
and `alert_details`, an 8-node transaction cycle):

```json
{
  "case_id": "CASE-000117",
  "risk": { "p": 0.9286, "margin": 0.8573, "ood": 5.8405 },
  "risk_band": "RED",
  "member_alert_ids": [],
  "accounts": ["800D7F3B0","80307A9E0","8042E41B0","804E71900","80567CFE0","805A06820","807214430","808112D30"],
  "transactions": [
    {"txn_id":"CASE-000117-TXN-0003095","from_account":"805A06820","to_account":"80307A9E0","amount":67802.05,"currency":"Yuan","timestamp":"2022-09-08T17:23:00","typology_flag":null,"xgb_score":0.9218},
    {"txn_id":"CASE-000117-TXN-0013810","from_account":"800D7F3B0","to_account":"8042E41B0","amount":8169.53,"currency":"Euro","timestamp":"2022-09-11T11:33:00","typology_flag":null,"xgb_score":0.9512},
    {"txn_id":"CASE-000117-TXN-0024513","from_account":"807214430","to_account":"80567CFE0","amount":664279.21,"currency":"Rupee","timestamp":"2022-09-10T10:37:00","typology_flag":null,"xgb_score":0.9135},
    {"txn_id":"CASE-000117-TXN-0028066","from_account":"80307A9E0","to_account":"807214430","amount":9300.86,"currency":"US Dollar","timestamp":"2022-09-08T19:15:00","typology_flag":null,"xgb_score":0.9528},
    {"txn_id":"CASE-000117-TXN-0046101","from_account":"808112D30","to_account":"805A06820","amount":9572.92,"currency":"US Dollar","timestamp":"2022-09-12T07:14:00","typology_flag":null,"xgb_score":0.9527},
    {"txn_id":"CASE-000117-TXN-0050502","from_account":"80567CFE0","to_account":"804E71900","amount":8692.16,"currency":"US Dollar","timestamp":"2022-09-10T15:44:00","typology_flag":null,"xgb_score":0.9524},
    {"txn_id":"CASE-000117-TXN-0067758","from_account":"804E71900","to_account":"800D7F3B0","amount":7417.89,"currency":"Euro","timestamp":"2022-09-11T11:20:00","typology_flag":null,"xgb_score":0.9506},
    {"txn_id":"CASE-000117-TXN-0086609","from_account":"8042E41B0","to_account":"808112D30","amount":8169.53,"currency":"Euro","timestamp":"2022-09-11T13:45:00","typology_flag":null,"xgb_score":0.9512}
  ],
  "graph_edges": [
    {"source":"805A06820","target":"80307A9E0","relation":"SENT","weight":0.9218},
    {"source":"800D7F3B0","target":"8042E41B0","relation":"SENT","weight":0.9512},
    {"source":"807214430","target":"80567CFE0","relation":"SENT","weight":0.9135},
    {"source":"80307A9E0","target":"807214430","relation":"SENT","weight":0.9528},
    {"source":"808112D30","target":"805A06820","relation":"SENT","weight":0.9527},
    {"source":"80567CFE0","target":"804E71900","relation":"SENT","weight":0.9524},
    {"source":"804E71900","target":"800D7F3B0","relation":"SENT","weight":0.9506},
    {"source":"8042E41B0","target":"808112D30","relation":"SENT","weight":0.9512}
  ],
  "entities": [
    {"id":"800D7F3B0","type":"Account","name":"A/c 800D7F3B0","owner_pan":"SXTLL5320D","director_of":null,"kyc_status":"VERIFIED","entity_subtype":"Individual","jurisdiction":"Standard","linked_company":null},
    {"id":"80307A9E0","type":"Account","name":"A/c 80307A9E0","owner_pan":"DETTQ8606K","director_of":null,"kyc_status":"VERIFIED","entity_subtype":"Individual","jurisdiction":"Standard","linked_company":null},
    {"id":"8042E41B0","type":"Account","name":"A/c 8042E41B0","owner_pan":"XOMQW7702W","director_of":null,"kyc_status":"VERIFIED","entity_subtype":"Individual","jurisdiction":"Standard","linked_company":null},
    {"id":"804E71900","type":"Account","name":"A/c 804E71900","owner_pan":"QFPLE5644N","director_of":null,"kyc_status":"VERIFIED","entity_subtype":"Registered Business","jurisdiction":"Standard","linked_company":null},
    {"id":"80567CFE0","type":"Account","name":"A/c 80567CFE0","owner_pan":"FIXZJ3889Z","director_of":null,"kyc_status":"VERIFIED","entity_subtype":"Individual","jurisdiction":"Standard","linked_company":null},
    {"id":"805A06820","type":"Account","name":"A/c 805A06820","owner_pan":"ODAOI1277D","director_of":null,"kyc_status":"VERIFIED","entity_subtype":"Registered Business","jurisdiction":"Standard","linked_company":null},
    {"id":"807214430","type":"Account","name":"A/c 807214430","owner_pan":"EUMSF1106C","director_of":null,"kyc_status":"VERIFIED","entity_subtype":"Registered Business","jurisdiction":"Standard","linked_company":null},
    {"id":"808112D30","type":"Account","name":"A/c 808112D30","owner_pan":"HKYOA0314U","director_of":null,"kyc_status":"VERIFIED","entity_subtype":"Registered Business","jurisdiction":"Standard","linked_company":null}
  ],
  "shared_pan_groups": [],
  "alert_details": []
}
```

Note: this case's 8 transactions form a *cycle* (A→B→C→D→E→F→G→H→A) — a
classic "round-tripping" / layering pattern — but because the reasoning
service's cycle detector caps at 6 hops (a documented, honest limitation, not a
hidden bug), it does NOT get flagged as a `circular_flow` relationship
automatically. This case, when investigated, actually **fails the evidence
gate** (see §3.5) because it has zero detected relationships and zero rule
alerts, despite being RED-banded purely on ML score. Build your UI to make this
state ("high risk score, but insufficient evidence to draft a report")
understandable to a user rather than confusing — it's a real, meaningful
outcome, not an error state.

---

### 3.4 `POST /evidence/{case_id}`

Assembles the **evidence pack** for a case — this is the deterministic,
non-AI-generated evidence layer (transactions, relationships, KYC flags, rule
alerts, regulation citations) that gets shown to the analyst *before* any
Gemma reasoning happens, and is also what gets fed into the Gemma investigation
prompt.

- No request body needed in the normal flow (case is fetched server-side).
- Optionally accepts a `Case` object in the body if you want to evaluate
  evidence for a case not yet known to the server.

**Response shape:**
```ts
type EvidenceItem = {
  ev_id: string;        // "EV-001", "EV-002", ... — stable, referenced later by the AI narration
  kind: string;         // "transaction" | "relationship" | "rule_alert" | "kyc_flag" | "document" | "regulation" | "risk_score"
  source_ref: string;   // traceability pointer — a txn_id, an account id, a regulation section, etc.
  value: string;        // human-readable evidence line, ready to display as-is
}

type Relationship = {
  type: string;          // "linked_pan" | "repeat_beneficiary" | "funnel_account" | "circular_flow" | "shared_director"
  entities: string[];    // the account/PAN/person ids involved
}

type EvidencePack = {
  case_id: string;
  evidence: EvidenceItem[];
  timeline: { ts: string; event: string }[];   // chronological, human-readable events — includes synthesized "VELOCITY: ..." summary events
  relationships: Relationship[];
  regulations: { section: string; text_snippet: string; relevance: string }[];
  risk: RiskScore;
  missing_evidence: string[];   // NON-EMPTY means the case fails the evidence gate — see §3.5
}
```

**Real captured response** (`CASE-000117` — the gate-FAILING example):
```json
{
  "case_id": "CASE-000117",
  "evidence": [
    {"ev_id":"EV-001","kind":"transaction","source_ref":"CASE-000117-TXN-0003095","value":"805A06820 -> 80307A9E0 67,802 Yuan (exact: 67802.05 Yuan) on 2022-09-08T17:23:00, XGBoost anomaly score 0.92"},
    {"ev_id":"EV-002","kind":"transaction","source_ref":"CASE-000117-TXN-0028066","value":"80307A9E0 -> 807214430 $9,301 (exact: 9300.86 US Dollar) on 2022-09-08T19:15:00, XGBoost anomaly score 0.95"},
    {"ev_id":"EV-003","kind":"transaction","source_ref":"CASE-000117-TXN-0024513","value":"807214430 -> 80567CFE0 ₹6,64,279 (exact: 664279.21 Rupee) on 2022-09-10T10:37:00, XGBoost anomaly score 0.91"},
    {"ev_id":"EV-009","kind":"risk_score","source_ref":"probe:CASE-000117","value":"Gemma activation-probe risk p=0.93, margin=0.86, ood=5.84, band=RED"},
    {"ev_id":"EV-010","kind":"regulation","source_ref":"PML Rules 2005, Rule 2(1)(g)","value":"PML Rules 2005, Rule 2(1)(g): 'Suspicious transaction' means a transaction, whether or not made in cash, which to a person acting in good faith gives rise to a reasonable ground of suspicion that it may involve..."}
  ],
  "timeline": [
    {"ts":"2022-09-08T17:23:00","event":"CASE-000117-TXN-0003095: 805A06820 sent 67,802 Yuan to 80307A9E0"},
    {"ts":"2022-09-08T19:15:00","event":"CASE-000117-TXN-0028066: 80307A9E0 sent $9,301 to 807214430"}
  ],
  "relationships": [],
  "regulations": [
    {"section":"PML Rules 2005, Rule 2(1)(g)","text_snippet":"'Suspicious transaction' means a transaction...","relevance":"Suspicious transaction definition (match score 0.81)"}
  ],
  "risk": {"p":0.9286,"margin":0.8573,"ood":5.8405},
  "missing_evidence": [
    "relationship: requires at least one entity relationship (linked PAN / shared director / repeat beneficiary / circular flow)"
  ]
}
```

**Real captured response** (`CASE-000006` — the gate-PASSING example, evidence
array truncated for length, full case has 54 evidence items):
```json
{
  "case_id": "CASE-000006",
  "evidence": [
    {"ev_id":"EV-041","kind":"relationship","source_ref":"graph:linked_pan:0","value":"linked pan: PAN-TUOTE8885C , 8000C76D0 , 8006FA4B0 , ... (30 accounts total)"},
    {"ev_id":"EV-042","kind":"relationship","source_ref":"graph:funnel_account:1","value":"funnel account: 808E44B10 , 8006FA4B0 , ... (12 accounts total)"},
    {"ev_id":"EV-044","kind":"rule_alert","source_ref":"alert:velocity:808E44B10","value":"velocity rule on 808E44B10: 14 outbound transactions within a 48h window totalling 4,879,976"},
    {"ev_id":"EV-046","kind":"rule_alert","source_ref":"alert:threshold:8113EEDB0","value":"threshold rule on 8113EEDB0: Transfer of 998,089 to 8053B01E0 just under the 1,000,000 reporting threshold"},
    {"ev_id":"EV-049","kind":"kyc_flag","source_ref":"kyc:8000C76D0|8006FA4B0|...","value":"19 accounts share the same risk profile — KYC FAILED, Shell Company, High Risk jurisdiction, all linked to Aurora Ventures Pvt Ltd: 8000C76D0, 8006FA4B0, ... (+11 more)"},
    {"ev_id":"EV-051","kind":"risk_score","source_ref":"probe:CASE-000006","value":"Gemma activation-probe risk p=0.93, margin=0.86, ood=13.67, band=RED"}
  ],
  "relationships": [
    {"type":"linked_pan","entities":["PAN-TUOTE8885C","8000C76D0","8006FA4B0","...","8113EEDB0"]},
    {"type":"funnel_account","entities":["808E44B10","8006FA4B0","...","80D8F53F0"]},
    {"type":"funnel_account","entities":["8053B01E0","8000C76D0","...","8113EEDB0"]}
  ],
  "missing_evidence": []
}
```

**UI implications — this is your "Evidence" tab/panel:**
- Group `evidence[]` by `kind` into labeled sections: Transactions, Relationships,
  Rule Alerts, KYC Flags, Documents, Regulations, Risk Score. Each `EvidenceItem`
  is a single row/card: show `value` as the main text, `ev_id` as a small
  monospace badge (`EV-041`), `source_ref` as a secondary/tooltip detail.
- `kyc_flag` items are pre-aggregated server-side (e.g. "19 accounts share the
  same risk profile...") — do not try to re-group them further, just render
  the string.
- **`missing_evidence` is a critical UI signal.** If non-empty, prominently show
  a "this case cannot be filed as an STR yet" banner listing each missing item
  in plain language, and disable/gray out the "Run Investigation" or "Draft STR"
  call-to-action (though the investigate endpoint can still technically be
  called — it will just return `INSUFFICIENT_EVIDENCE`, see §3.5). Treat this
  as a real, load-bearing gate in the UI, not decoration.
- `timeline[]` is ready-made for a vertical timeline component — sort by `ts`
  ascending (already sorted), render `event` as the row text. Rows starting
  with `"VELOCITY:"` are synthesized summary rows (not a single transaction) —
  worth a distinct icon/style.
- `regulations[]` (top-level, separate from the `evidence` items of
  `kind:"regulation"` — same data, different shape) is convenient for a
  dedicated "Applicable Regulations" card: `section` as a bold heading,
  `text_snippet` as body text, `relevance` as a small caption (it includes a
  similarity match score, e.g. "(match score 0.81)" — can show as a percentage
  or just the descriptive text before the parenthetical).

---

### 3.5 `POST /investigate/{case_id}`

**This is the main "AI investigation" action** — runs a single Gemma pass under
schema-constrained decoding to produce an investigation summary and (if
evidence permits) a full STR draft. This is a **slow, expensive call — 60 to
90+ seconds** in practice (real measured: 65–87 seconds per case on a 4B local
Gemma model). **The UI must show a prominent loading/progress state for this
entire duration** — do not let it look like a hung page. A good pattern: a
multi-step progress indicator narrating what's happening ("Reviewing evidence…
Determining pattern… Checking sufficiency… Drafting narration…") even if it's
not literally streaming — the backend does not stream, it returns once at the
end.

- No request body needed in the normal flow.
- Returns 503 if Ollama/the model is unreachable — show a clear "AI service
  unavailable, try again" error state distinct from a 404 (case not found) or
  a 200 with `status: "INSUFFICIENT_EVIDENCE"` (a valid, expected outcome, not
  an error).

**Response shape:**
```ts
type NarrationSentence = {
  sentence: string;
  confidence: number;   // 0.0–1.0 — fused score: model's own token-logprob confidence, discounted by an independent grounding check against real ledger data
  band: "green" | "yellow" | "red";   // green > 0.75, yellow 0.5–0.75, red < 0.5 (also force-capped to red if the sentence cites an unverifiable figure)
}

type STRDraft = {
  case_id: string;
  gos_tag: string;                 // "ground of suspicion" — a closed-vocabulary tag, see §3.5.1 for the exact list
  narration: NarrationSentence[];  // the actual STR report text, sentence by sentence, each independently confidence-scored
  recommended_action: string;      // closed vocabulary — see §3.5.1
  amounts_cited: number[];         // every rupee/currency figure the AI cited — cross-checked against the real ledger
  evidence_refs: string[];         // which EV-xxx items the AI actually used
}

type InvestigationResult = {
  case_id: string;
  investigation_summary: string;      // a short paragraph — the human-readable "what's going on" summary
  behaviour_pattern: string;           // a paragraph describing the specific pattern detected, with inline [EV-xxx] citations
  suggested_questions: string[];       // follow-up investigative questions for a human analyst
  str_draft: STRDraft | null;          // NULL when status is INSUFFICIENT_EVIDENCE
  status: "OK" | "INSUFFICIENT_EVIDENCE";
}
```

**Real captured response** (`CASE-000006` — full success path):
```json
{
  "case_id": "CASE-000006",
  "investigation_summary": "The investigation reveals significant red flags across KYC, transaction patterns, and velocity metrics. Multiple accounts linked to Aurora Ventures Pvt Ltd share a 'Shell Company' profile and are flagged as high risk [EV-049, EV-050]. The activity shows clear signs of layering and structuring; for example, transactions were flagged for smurfing in multiple currencies [EV-006, EV-021, EV-034]. Furthermore, the accounts involved have triggered velocity alerts [EV-044, EV-045] and specific threshold alerts suggesting attempts to stay below reporting limits [EV-047, EV-048]. The overall risk score is high (p=0.93) [EV-051].",
  "behaviour_pattern": "The evidence demonstrates multiple instances of coordinated financial activity involving accounts linked by shared identifiers and exhibiting common risk profiles. Specific patterns include: 1) Structuring/Smurfing attempts... 2) High velocity and volume alerts were triggered... 3) KYC flags indicate multiple linked accounts share a 'Shell Company' profile...",
  "suggested_questions": [
    "What is the beneficial ownership structure for the accounts linked via PAN-TUOTE8885C and associated with Aurora Ventures Pvt Ltd? [EV-049]",
    "Can the source of funds for the high-value transactions (e.g., 167361853.53 Rupee [EV-023]) be verified against legitimate business operations?",
    "What is the economic rationale connecting the multiple, disparate cross-border transfers flagged as smurfing? [EV-009, EV-021]",
    "Are there any internal policies that govern the aggregation or onward transfer of funds received via 'funnel' accounts like 8053B01E0? [EV-043]"
  ],
  "str_draft": {
    "case_id": "CASE-000006",
    "gos_tag": "USE_OF_SHELL_OR_CONNECTED_ENTITIES",
    "narration": [
      {"sentence":"The investigation identified multiple accounts linked to a common identifier (PAN-TUOTE8885C) that share the risk profile of 'Shell Company' and operate in high-risk jurisdictions [EV-049].","confidence":0.688,"band":"yellow"},
      {"sentence":"These linkages suggest coordinated activity among connected entities, including 8000C76D0, 801798880, and 8053B01E0 [EV-049].","confidence":0.45,"band":"red"},
      {"sentence":"The transaction history includes multiple instances of structuring and smurfing across various currencies (e.g., US Dollar [EV-006], Canadian Dollar [EV-009], Australian Dollar [EV-030]) [EV-006, EV-009, EV-030].","confidence":0.768,"band":"green"},
      {"sentence":"Specific transactions were flagged for structuring due to amounts being close to reporting thresholds (e.g., 975628.1 Rupee [EV-039], 967537.34 Rupee [EV-018]) [EV-047, EV-048].","confidence":0.834,"band":"green"},
      {"sentence":"The accounts involved have demonstrated high activity velocity and volume, triggering alerts for excessive transactions and total value transfers [EV-044, EV-045].","confidence":0.5,"band":"red"},
      {"sentence":"These patterns are consistent with the use of interconnected shell entities to disguise the aggregate scale or origin of funds [EV-052, EV-053].","confidence":0.687,"band":"yellow"}
    ],
    "recommended_action": "FILE_STR_WITH_FIU_IND",
    "amounts_cited": [18611.96, 4389.01, 4795.61, 6603.64, 692.25, 8726.14, 12449.87, 167361853.53, 998088.94, 975628.1],
    "evidence_refs": ["EV-001","EV-002","EV-003","EV-004","EV-005","EV-006","EV-007","EV-008","EV-009","EV-010","EV-011","EV-012"]
  },
  "status": "OK"
}
```

**Real captured response** (`CASE-000117` — the INSUFFICIENT_EVIDENCE path; the
system correctly refuses to draft an STR for a high-risk-scored but
under-evidenced case):
```json
{
  "case_id": "CASE-000117",
  "investigation_summary": "Investigation halted by the evidence validator. The following critical evidence is missing or unbacked: relationship: requires at least one entity relationship (linked PAN / shared director / repeat beneficiary / circular flow)",
  "behaviour_pattern": "UNDETERMINED — insufficient evidence",
  "suggested_questions": [
    "Can additional transaction history be pulled for the involved accounts?",
    "Are there KYC documents or entity linkages not yet ingested for this cluster?",
    "Does the alerting rule that created this case have supporting context to attach?"
  ],
  "str_draft": null,
  "status": "INSUFFICIENT_EVIDENCE"
}
```

**UI implications — this is your "Investigation" / "AI Analysis" tab:**
- On `status === "INSUFFICIENT_EVIDENCE"`: show `investigation_summary` as an
  explanatory banner (it already explains *why*, in plain English), show
  `suggested_questions` as an actionable checklist for what a human should go
  gather next, and **do not** show any STR/export UI at all — there is nothing
  to export (`str_draft` is `null`). This is a legitimate, designed outcome —
  message it as "not enough evidence to draft a filing yet," not as a failure
  or bug.
- On `status === "OK"`: show `investigation_summary` and `behaviour_pattern` as
  the headline AI narrative (render `[EV-xxx]` citations as clickable chips
  that jump to/highlight the corresponding evidence item if you're building a
  linked evidence panel — nice-to-have, not required). Show
  `suggested_questions` as a follow-up checklist.
- **The STR draft (`str_draft`) is the centerpiece deliverable — build a
  dedicated, prominent view for it:**
  - `gos_tag`: show as a formatted badge/label (see §3.5.1 for a human-readable
    label mapping — don't show the raw enum string as-is to an end user without
    at least inserting spaces/title-casing it).
  - `narration[]`: render each sentence as its own block/paragraph, with a
    **left border or background tint colored by `band`** (green/yellow/red) —
    this is THE signature visual of the whole product: a confidence heat-map
    over the actual report text. Show the numeric `confidence` (as a
    percentage) on hover or as a small badge next to each sentence. A yellow or
    red sentence should read as "verify this claim before you sign off" — some
    explicit affordance (tooltip, icon) communicating that meaning is strongly
    recommended, not just the color alone (accessibility — never rely on color
    alone to convey the confidence level; pair with an icon or label).
  - `amounts_cited`: list as a set of currency-formatted chips/tags — see §6
    for exact currency formatting since these are cross-currency case-dependent
    values.
  - `evidence_refs`: list as small `EV-xxx` badges, ideally clickable/linked
    back to the Evidence tab.
  - `recommended_action`: a prominent badge/label — see §3.5.1 for the exact
    vocabulary.

#### 3.5.1 Closed vocabularies for `gos_tag` and `recommended_action`

These are **exactly** the only values Gemma is structurally permitted to
produce (enforced via schema-constrained decoding — the model cannot emit
anything outside this list, it's not just convention):

```
gos_tag (Ground of Suspicion):
  STRUCTURING_TO_AVOID_REPORTING_THRESHOLD
  SMURFING_DISPERSED_SMALL_CREDITS
  LAYERING_THROUGH_MULTIPLE_ACCOUNTS
  ROUND_TRIPPING_CIRCULAR_FLOW
  USE_OF_SHELL_OR_CONNECTED_ENTITIES
  TRANSACTIONS_INCONSISTENT_WITH_CUSTOMER_PROFILE
  UNEXPLAINED_SUDDEN_INCREASE_IN_ACTIVITY
  NO_ECONOMIC_RATIONALE

recommended_action:
  FILE_STR_WITH_FIU_IND
  ENHANCED_DUE_DILIGENCE_AND_MONITOR
  REQUEST_ADDITIONAL_DOCUMENTS
  NO_ACTION_CLOSE_ALERT
```

Suggested v0 label mapping (title-case, spaces, no underscores) for display:
`STRUCTURING_TO_AVOID_REPORTING_THRESHOLD` → "Structuring to Avoid Reporting
Threshold", etc. — mechanical transform, no special-casing needed beyond
underscore→space and title-case.

---

### 3.6 `GET /investigate/{case_id}/full`

Returns the **cached** result of the most recent investigation run for a case,
**plus the evidence pack and run diagnostics** — this is the endpoint to call
when a user navigates back to a case they already investigated, so you don't
re-run the (slow, expensive) Gemma call every time. Returns **404** if no
investigation has been run yet for this case (i.e., call `POST
/investigate/{case_id}` first, then this endpoint for subsequent views).

**Recommended v0 flow:** on opening a case detail page, try `GET
/investigate/{case_id}/full` first; if 404, show the "Run Investigation" call
to action (which calls `POST /investigate/{case_id}`); once that succeeds,
either use its response directly or immediately re-fetch `/full` for the
combined view.

**Response shape:**
```ts
type FullInvestigation = {
  result: InvestigationResult;      // exactly the shape from §3.5
  evidence: EvidencePack;           // exactly the shape from §3.4
  diagnostics: {
    model: string;                  // e.g. "gemma4-sentinel"
    logprobs_available: boolean;
    total_tokens: number;           // full generation length including internal "thinking" tokens
    answer_tokens: number;          // just the final structured answer portion
    overall_confidence: number;     // 0–1, mean of all narration sentence confidences
    amount_violations: string[];    // non-empty = the AI cited a figure that could NOT be verified against the ledger (a real trust signal — should be empty in healthy runs)
    evidence_assessment: { ev_id: string; observation: string }[];   // the AI's own restatement of each evidence item it considered — step 1 of its 6-step reasoning process
    model_sufficiency: "SUFFICIENT" | "INSUFFICIENT" | null;   // the model's OWN judgment call on evidence sufficiency (separate/independent from the deterministic gate)
    elapsed_s: number;               // wall-clock seconds the investigation took
  }
}
```

**Real captured response** (`CASE-000006`, diagnostics portion — full
result/evidence sections are identical to §3.4/§3.5 examples above):
```json
{
  "diagnostics": {
    "model": "gemma4-sentinel",
    "logprobs_available": true,
    "total_tokens": 3604,
    "answer_tokens": 2269,
    "overall_confidence": 0.654,
    "amount_violations": [],
    "evidence_assessment": [
      {"ev_id":"EV-001","observation":"A transaction of 4389.01 UK Pound occurred on 2022-09-01, flagged with a high anomaly score (0.92) [EV-001]."},
      {"ev_id":"EV-002","observation":"A transaction of 4795.61 UK Pound occurred on 2022-09-01, flagged with a high anomaly score (0.93) [EV-002]."}
    ],
    "model_sufficiency": "SUFFICIENT",
    "elapsed_s": 86.7
  }
}
```

**UI implications:** `diagnostics` is a great candidate for a small "Run Info"
/ "Model Diagnostics" expandable panel — not the primary content, but valuable
for a "how was this generated" transparency section (a strong feature for a
compliance-facing tool: show your work). `amount_violations` being non-empty
is worth a visible warning badge ("⚠ N unverifiable figures detected") since it
means the grounding check actually caught something. `evidence_assessment`
gives you a nice "step-by-step reasoning trace" you could render as a
collapsible list showing the AI's evidence-by-evidence restatement before its
conclusion — good for building trust/transparency into the UI.

---

### 3.7 `GET /regulations/search?q=<query>&k=<3>`

Standalone semantic search over the regulation corpus (PMLA/RBI/FIU-IND
sections). `q` required, min length 2. `k` optional, 1–10, default 3.

**Real captured response** (`?q=structuring&k=2`):
```json
[
  {"section":"PML Rules 2005, Rule 3(1)(B)","text_snippet":"Reporting entities shall maintain records of all series of cash transactions integrally connected to each other which have been individually valued below rupees ten lakh where such series of transactions have taken place within a month and the monthly aggregate exceeds rupees ten lakh. Splitting amounts to remain below the threshold is the classic indicator of structuring.","relevance":"Integrally connected cash transactions (match score 0.85)"},
  {"section":"FIU-IND STR Guidance, Red Flag 4.2","text_snippet":"Multiple transactions individually kept marginally below the prescribed reporting threshold...","relevance":"Transactions just below reporting thresholds (match score 0.79)"}
]
```

**UI implication:** Good for a standalone "Regulation Lookup" search box/page
(a compliance-officer research tool independent of any specific case) — a
search input, results as cards exactly like the `regulations[]` shown in the
evidence pack.

---

### 3.8 `POST /export/{case_id}?actor=<name>`

Exports an STR draft as FIU-IND-formatted XML and **permanently writes an audit
log entry** — this is effectively "attest and file" in the UI. Requires the
full `STRDraft` object (from a prior `/investigate` call) as the request body.
`actor` query param (default `"analyst"`) should be the name of the person
attesting — **a v0 frontend should collect this from a text input or the
logged-in user's name before calling this**, since it's recorded permanently in
the tamper-evident audit log.

**Request body:** the exact `STRDraft` object from `investigation_result.str_draft`.

**Response shape:**
```ts
type ExportResponse = {
  xml: string;              // the full FIU-IND STR XML document, ready to download/display
  audit_entry: {             // the audit log row that was just written
    seq: number;
    ts: string;
    actor: string;
    action: string;          // "STR_ATTESTED_AND_EXPORTED"
    case_id: string;
    evidence_refs: string[];
    detail: object;
    prev_hash: string;
    hash: string;
  }
}
```

**UI implication:** This should be a deliberate, confirmable action — e.g. an
"Attest & Export" button behind a confirmation dialog ("You are about to
attest this STR as [actor name]. This is recorded permanently."), not a casual
click. On success: offer the `xml` as a downloadable file (e.g.
`STR_{case_id}.xml`, `Blob`/`URL.createObjectURL` in the browser) and show a
success state referencing the `audit_entry.seq` number ("Filed — audit record
#34").

---

### 3.9 `GET /audit/verify`

Verifies the integrity of the hash-chain audit log.

**Real captured response:**
```json
{ "intact": true, "length": 34 }
```

**UI implication:** A simple integrity-status widget — green check + "Audit
log intact (34 entries)" if `intact: true`; a prominent red warning if `false`
(would indicate tampering — should never realistically happen, but worth
surfacing if you build an audit/compliance page).

---

### 3.10 `GET /audit/{case_id}`

Full audit trail for one case — every evidence-assembly, investigation, and
export event, in order.

**Real captured response** (truncated, one entry shown):
```json
[
  {
    "seq": 20,
    "ts": "2026-07-18T09:43:02.997541+00:00",
    "actor": "system",
    "action": "INVESTIGATION_RUN",
    "case_id": "CASE-000006",
    "evidence_refs": ["EV-001","EV-002","...","EV-054"],
    "detail": {},
    "prev_hash": "...",
    "hash": "..."
  }
]
```

Possible `action` values you'll see in practice: `"EVIDENCE_ASSEMBLED"`,
`"INVESTIGATION_RUN"`, `"STR_ATTESTED_AND_EXPORTED"`.

**UI implication:** A per-case "History" / "Audit Trail" tab — render as a
simple reverse-chronological list: `ts` (formatted date/time), `action` (as a
badge/label — map to friendly text: "Evidence assembled", "Investigation run",
"STR attested & exported"), `actor`. `seq`/`hash`/`prev_hash` are there for
integrity verification, not typically shown to an end user unless building a
technical/compliance-audit-focused view.

---

### 3.11 `GET /schema/str`

Returns the exact JSON schema used to constrain Gemma's generation — mostly
useful for a "how does this work" / transparency page, or to drive the
`gos_tag`/`recommended_action` dropdown options dynamically instead of
hardcoding the lists in §3.5.1.

**Real captured response:**
```json
{
  "schema": { "...": "the full JSON schema object" },
  "gos_tags": ["STRUCTURING_TO_AVOID_REPORTING_THRESHOLD", "..."],
  "recommended_actions": ["FILE_STR_WITH_FIU_IND", "..."]
}
```

---

### 3.12 `POST /grammar/validate`

**Powers a specific, high-value demo widget: "try to break the AI's output
format."** Takes arbitrary pasted text/JSON and checks it against the same
schema Gemma is constrained by, explaining exactly why it would be rejected.
This exists to demonstrate that the AI's output format is *structurally*
guaranteed valid, not just usually valid.

**Request:** `{"raw": "<any string, ideally malformed JSON or a JSON object with an invalid gos_tag>"}`

**Real captured response** (deliberately invalid input:
`{"gos_tag":"LOOKS_SUSPICIOUS"}`):
```json
{
  "valid": false,
  "error": "missing required field 'evidence_assessment'; missing required field 'behaviour_pattern'; missing required field 'evidence_sufficiency'; missing required field 'investigation_summary'; missing required field 'suggested_questions'; missing required field 'narration'; missing required field 'amounts_cited'; missing required field 'recommended_action'; gos_tag 'LOOKS_SUSPICIOUS' is outside the closed FIU dictionary — under constrained decoding these tokens are unreachable",
  "checks_failed": [
    "required:evidence_assessment", "required:behaviour_pattern", "required:evidence_sufficiency",
    "required:investigation_summary", "required:suggested_questions", "required:narration",
    "required:amounts_cited", "required:recommended_action", "enum:gos_tag"
  ]
}
```

**UI implication — build this as a small interactive playground widget**, e.g.
on a "How It Works" or "Trust & Safety" page: a text area where a user can
paste/type a JSON fragment, a "Validate" button, and a clear
pass/fail result showing `error` as a readable message and `checks_failed` as
a list of specific violated rules. This is a genuinely compelling, tangible way
to demonstrate the constrained-decoding guarantee to a non-technical viewer —
worth good visual treatment (e.g. a red/green result panel, syntax-highlighted
input).

---

## 4. End-to-end user flow (recommended page/screen structure for v0)

```
1. Dashboard (case list)
   GET /health           → status indicator in header
   GET /cases            → sortable/filterable table or card grid, grouped by risk_band

2. Case Detail (tabs or sections within one page)
   GET /cases/{id}                    → header info: case_id, risk badge, account count, txn count
   POST /evidence/{id}                → "Evidence" tab: transactions, relationships, KYC flags, rule alerts, regulations
   GET /investigate/{id}/full  (or)
   POST /investigate/{id}             → "AI Investigation" tab: summary, behaviour pattern, questions, STR draft w/ heat-map
   GET /audit/{id}                    → "History" tab: audit trail

3. STR Draft / Export (within Case Detail, once investigated + status=="OK")
   → render str_draft with the confidence heat-map (signature UI element)
   → "Attest & Export" button → POST /export/{id} → download XML, show audit confirmation

4. (Optional, secondary) Regulation Search page
   GET /regulations/search?q=...

5. (Optional, secondary) Trust & Safety / How It Works page
   GET /schema/str
   POST /grammar/validate            → interactive "try to break it" widget
   GET /audit/verify                 → chain integrity status

6. (Optional, admin) Model Comparison page — talks to ENGINE (port 8001) directly
   GET /metrics/comparison/full      → bar chart comparing gemma_probe / xgboost / rule_count
   POST /risk/threshold              → a slider that recomputes and shows new red/yellow/green counts
```

---

## 5. Error handling reference

| Situation | HTTP status | Body shape | UI treatment |
|---|---|---|---|
| Unknown `case_id` | 404 | `{"detail": "..."}` | "Case not found" empty state |
| Malformed query params (e.g. `threshold` out of 0–1 range) | 422 | `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}` (FastAPI validation error array) | Generic "invalid request" toast; these should mostly be prevented client-side by input validation, not surfaced raw to users |
| Ollama/model unreachable during `/investigate` | 503 | `{"detail": "Investigation failed (...). Is Ollama serving ... ?"}` | "AI service temporarily unavailable, please try again" — distinct from a 404 or a valid `INSUFFICIENT_EVIDENCE` result |
| No investigation run yet, calling `/investigate/{id}/full` | 404 | `{"detail": "No investigation has been run for this case yet"}` | Trigger the "Run Investigation" CTA instead of showing an error |
| `case_id` in path vs. body mismatch on `/export` | 422 | `{"detail": "case_id in path and STRDraft body disagree"}` | Should not occur in normal flow if you always pass the `str_draft` object exactly as received from `/investigate` |

**General rule for v0:** never show a raw `{"detail": ...}` object to the end
user. Map known cases (above) to friendly messages; for anything unexpected,
show a generic "Something went wrong, please try again" toast and log the raw
error to the console/telemetry.

---

## 6. Currency formatting — exact reference implementation

The real dataset spans multiple currencies (confirmed present in live data:
`US Dollar`, `Euro`, `UK Pound`, `Rupee`, `Yuan`, `Canadian Dollar`, `Swiss
Franc`, `Ruble`, `Brazil Real`, `Australian Dollar`). **Do not hardcode ₹-only
formatting.** Use this exact symbol map (case-insensitive match on the
`currency` field, matching the backend's own formatting logic):

```js
const CURRENCY_SYMBOLS = {
  inr: "₹", rupee: "₹", "indian rupee": "₹",
  usd: "$", "us dollar": "$",
  eur: "€", euro: "€",
  gbp: "£", "uk pound": "£", pound: "£",
  yen: "¥", jpy: "¥",
};

function formatAmount(amount, currency = "") {
  const sym = CURRENCY_SYMBOLS[(currency || "").trim().toLowerCase()];
  if (sym === "₹")
    return "₹" + Number(amount).toLocaleString("en-IN", { maximumFractionDigits: 0 });
  const grouped = Number(amount).toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (sym) return sym + grouped;
  return currency ? `${grouped} ${currency}` : grouped;   // unknown currency: show the raw name, e.g. "67,802 Yuan"
}
```

Rupee amounts use Indian digit grouping (₹24,55,000 not ₹2,455,000); every
other currency uses western grouping with its symbol; unrecognized currency
names (e.g. `"Yuan"`, `"Ruble"`, `"Brazil Real"` — these have no symbol in the
map above) fall back to `"<grouped number> <currency name>"`, e.g. `"67,802
Yuan"` — exactly matching what appears in real evidence/timeline strings from
the backend, so your UI's number formatting will visually match the backend's
own pre-formatted text.

---

## 7. Visual/design signals worth carrying into a new frontend

These aren't API contract, but are meaningful product decisions worth
preserving in any new UI:

- **Raw evidence vs. AI-generated content must look visually distinct
  everywhere.** The existing frontend tags evidence panels with a small "⬒ Raw
  evidence" badge and AI output with "✦ Gemma-generated" — carry this
  distinction into v0's design so a user can always tell "did a person/rule
  produce this, or did the AI write this."
- **Confidence bands must never rely on color alone.** Pair green/yellow/red
  with an icon and/or text label (e.g. "green — confident", "yellow —
  review", "red — verify") for accessibility.
- **Risk bands (`RED`/`YELLOW`/`GREEN`) and confidence bands
  (`green`/`yellow`/`red`) are two DIFFERENT things that happen to share a
  color vocabulary** — one is "how risky is this case" (from the ML probe),
  the other is "how much should you trust this specific AI-written sentence."
  Don't conflate them visually; consider a different shape/position convention
  for each (e.g. risk band = a badge chip near the case title; confidence band
  = a left-border tint on narration text).
- **Empty evidence states are common and meaningful, not bugs** —
  `shared_pan_groups: []`, `alert_details: []`, `relationships: []` all occur
  on real, valid, even high-risk cases. Design empty states that read as
  informative ("No shared-PAN rings detected in this case") rather than
  broken.
