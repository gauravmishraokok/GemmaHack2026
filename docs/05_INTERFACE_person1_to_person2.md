# INTERFACE CONTRACT — Person 1 (engine :8001) → Person 2 (reasoning :8002)

**Status:** authoritative for integration. Written by Person 2 after building the
full reasoning + frontend stack. Where this document and Person 1's architecture
doc disagree, this document is the target both sides converge to — because the
reasoning pipeline, the confidence grounding, and the frontend are all already
coded against exactly these field names and shapes.

Read this top to bottom once. The single most important section is **§3
(the extended contract)** — there are new fields your architecture doc promises
(`shared_pan_groups`, `xgb_score`, `kyc_status`, `alert_details`) that are **not
yet in the frozen `shared_contracts.py`**, and we have to add them the same way
on both sides or the merge breaks.

---

## 0. TL;DR — what Person 2 needs from you

1. `GET /cases/{case_id}` returns a **`Case`** object that validates against the
   Pydantic models in §3. Person 2 calls this and does everything else.
2. `GET /cases` returns **`CaseSummary[]`**.
3. `GET /metrics/comparison` returns **`ComparisonMetric[]`** (frontend PR-AUC chart).
4. `POST /risk/threshold {"threshold": 0.6}` returns `{"red","yellow","green"}` counts.
5. Ship `engine/fixtures/hero_cases.json` = an array of full `Case` objects,
   **byte-compatible with §3**. Person 2 drops it into
   `reasoning/fixtures/mock_cases.json` and develops offline until your API is up.
6. On integration day Person 2 sets `ENGINE_API_URL=http://localhost:8001` and
   nothing else changes. That only works if every field below matches exactly.

---

## 1. How Person 2 consumes your Case (so you know what actually matters)

Person 2's pipeline is:

```
GET /cases/{id}  →  Case
   → evidence/builder.py       reads: transactions, graph_edges, entities, risk,
                                       accounts, + the new fields in §3
   → evidence/relationships.py reads: graph_edges[].relation, entities[].type,
                                       entities[].owner_pan
   → evidence/validator.py     HARD GATE: needs ≥3 transactions, ≥1 relationship,
                                       ≥1 regulation, every evidence item source-ref'd
   → investigation/pipeline.py Gemma drafts the STR, citing EV-ids
   → investigation/grounding.py verifies every ₹ amount the model cites exists in
                                Case.transactions[].amount (± aggregates)
```

**The two consequences you must care about:**

- **Every amount in `transactions[].amount` is treated as ground truth.** If the
  model cites a number not present there, our grounding verifier hard-caps that
  STR sentence into the red "verify this" band. So amounts must be the real,
  final rupee values — no placeholders, no rounding drift.
- **Relationships are re-derived by us from `graph_edges` + `entities`, not read
  from a field.** We detect `linked_pan`, `shared_director`, `repeat_beneficiary`,
  `funnel_account`, `circular_flow` ourselves. For that to fire you must emit the
  edges and entity fields described in §3.4 / §3.5. If you send transactions but
  no identity edges and no `owner_pan`, the case will trip our INSUFFICIENT_
  EVIDENCE gate (no relationship) even though it's a real laundering ring.

---

## 2. Field-name reconciliation (read this — it's where merges die)

Your architecture doc uses some names that differ from the frozen contract and
from Person 2's code. Here is the mapping we need you to emit. **Left = what you
described. Right = what Person 2's code reads.**

| Your doc | Emit as (contract) | Why |
|---|---|---|
| `sender_account` / `receiver_account` | `from_account` / `to_account` | frozen `Transaction` names; our whole pipeline uses these |
| `sender_pan` / `receiver_pan` | `entities[].owner_pan` (per account) | we derive `linked_pan` from `owner_pan`; PAN belongs on the entity, not the txn |
| `xgb_score` (on txn) | `Transaction.xgb_score` (NEW, §3.3) | we cite it as an ML anomaly signal in the STR |
| `sender_kyc_status` / `receiver_kyc_status` | `entities[].kyc_status` (NEW, §3.5) | KYC is an entity property, carried once per account |
| `entity_type` = "Shell Company" | `entities[].type` = `"Company"` **and** `entities[].kyc_status="FAILED"` | see §3.5 — `type` is a closed enum; "shell-ness" rides on `kyc_status`/`entity_subtype` |
| `shared_pan_groups` | `Case.shared_pan_groups` (NEW, §3.6) | first-class; becomes our lead evidence + a synthetic relationship |
| `alert_details` | `Case.alert_details` (NEW, §3.7) | rule-violation annotations we surface as evidence |
| `member_alert_ids` | `Case.member_alert_ids` | already in contract, unchanged |
| `risk_p` | `Case.risk.p` | frozen `RiskScore.p`; **not** a top-level `risk_p` |
| `margin` / `ood` | `Case.risk.margin` / `Case.risk.ood` | frozen `RiskScore` |

**Currency & IDs:** your data is IBM AML (account ids like `800428D50`,
currencies like `US Dollar`/`Euro`). That's fine — `Transaction.currency` is a
free string and we format per-currency. Just be **consistent**: the same account
id string must appear identically in `transactions`, `graph_edges`, `entities`,
`accounts`, and `shared_pan_groups`. We join on exact string match. A trailing
space or case difference silently drops a relationship.

---

## 3. The extended `Case` contract (add these to `shared_contracts.py` on BOTH sides)

The current frozen `shared_contracts.py` is missing four things your richer
pipeline produces. We add them as **optional fields with safe defaults** so
nothing that already validates breaks, and Person 2's fixtures (which don't have
them yet) still load. Apply this diff to the root `shared_contracts.py` and both
copies.

### 3.1 `Transaction` — add `xgb_score`

```python
class Transaction(BaseModel):
    txn_id: str
    from_account: str
    to_account: str
    amount: float
    currency: str = "INR"
    timestamp: datetime
    typology_flag: Optional[str] = None      # "structuring"|"layering"|"smurfing"|...
    xgb_score: Optional[float] = None         # NEW — per-txn ML anomaly score 0..1
```

- `typology_flag`: **lowercase**, one of `structuring | layering | smurfing |
  round_tripping | funnel | null`. We feed this string into the regulation query
  and the prompt. If a txn wasn't the reason for a rule flag, leave it `null`.
- `xgb_score`: the 0..1 score from Phase 4. We cite it verbatim
  ("XGBoost anomaly score 0.91"). Omit/`null` if unavailable — never fabricate.

### 3.2 `Entity` — closed `type` enum + KYC fields

```python
class Entity(BaseModel):
    id: str
    type: Literal["Account", "Person", "Company", "PAN"]   # closed — do NOT send "Shell Company"
    name: Optional[str] = None
    owner_pan: Optional[str] = None                         # REQUIRED on Account entities in a ring
    director_of: Optional[List[str]] = None
    # NEW (all optional):
    kyc_status: Optional[Literal["VERIFIED", "PENDING", "FAILED"]] = None
    entity_subtype: Optional[str] = None                    # "Shell Company"|"Individual"|"Registered Business"
    jurisdiction: Optional[str] = None                      # "High Risk"|"Standard"|...
    linked_company: Optional[str] = None
```

Critical rule: **`type` stays the 4-value enum.** A shell company is
`type="Company"`, `entity_subtype="Shell Company"`, `kyc_status="FAILED"`. If you
send `type="Shell Company"` our `Case.model_validate()` raises and the case is
dropped. This is the single most likely thing to break the merge — please grep
your entity-builder for the string "Shell Company" in a `type` field.

### 3.3 `Case` — add `shared_pan_groups` and `alert_details`

```python
class SharedPanGroup(BaseModel):        # NEW
    pan: str
    accounts: List[str]                 # ≥2 account ids controlled by one PAN

class AlertDetail(BaseModel):           # NEW
    account: str
    alert_type: Literal["velocity", "threshold", "structuring"]
    detail: str                         # human-readable, e.g. "6 txns in 48h totalling ₹59.2L"

class Case(BaseModel):
    case_id: str
    risk: RiskScore
    risk_band: Literal["RED", "YELLOW", "GREEN"]
    member_alert_ids: List[str]
    accounts: List[str]
    transactions: List[Transaction]
    graph_edges: List[GraphEdge]
    entities: List[Entity]
    # NEW (optional, default empty so old fixtures still load):
    shared_pan_groups: List[SharedPanGroup] = []
    alert_details: List[AlertDetail] = []
```

Person 2 will, on receiving these:
- turn each `SharedPanGroup` into a `linked_pan` relationship **even if you didn't
  emit LINKED_PAN edges** — it becomes lead evidence in the STR;
- surface each `AlertDetail` as a `kind="rule_alert"` evidence item with the
  `alert_type` as its source ref, so the model can cite "velocity rule: 6 txns/48h".

### 3.4 `GraphEdge` — unchanged, but emit identity edges

```python
class GraphEdge(BaseModel):
    source: str
    target: str
    relation: Literal["SENT", "OWNED_BY", "DIRECTOR_OF", "LINKED_PAN"]
    weight: Optional[float] = None
```

- `SENT`: one per confirmed transaction (or aggregated per pair). `weight` =
  xgb_score or txn count — either is fine, we only use it for edge thickness.
- `LINKED_PAN`: `source` = account id, `target` = the PAN node id (`"PAN-XXXXX"`).
  Emit these for ring accounts. (If you'd rather only send `shared_pan_groups`
  and skip LINKED_PAN edges, that's OK — we synthesise the relationship from the
  group. But if you send **both**, keep them consistent.)
- `OWNED_BY`: account → person/company. `DIRECTOR_OF`: person → company.
- **The graph served for a case must reference only entities present in
  `entities[]`.** A dangling edge to an id not in `entities` renders a ghost node
  in our graph view. Include every referenced node as an `Entity`.

### 3.5 `RiskScore` / `risk_band` — unchanged

```python
class RiskScore(BaseModel):
    p: float       # 0..1
    margin: float  # 0..1
    ood: float     # Mahalanobis distance; we display it, higher = less reliable
```

Bands: `RED p≥0.7`, `YELLOW p≥0.4`, else `GREEN`. Person 2 assumes these exact
cutoffs until `/risk/threshold` is wired. Keep them identical.

---

## 4. Exact JSON we expect from `GET /cases/{case_id}`

This is a complete, valid example (a structuring ring). **Copy its shape.** Every
field Person 2 reads is present. `entities` includes the PAN node so the graph
has no dangling edges.

```json
{
  "case_id": "CASE-000042",
  "risk": { "p": 0.91, "margin": 0.82, "ood": 1.42 },
  "risk_band": "RED",
  "member_alert_ids": ["ALR-1201", "ALR-1202", "ALR-1207"],
  "accounts": ["800428D50", "8004possibly2A1", "80051FF00"],
  "transactions": [
    {
      "txn_id": "CASE-000042-TXN-90001",
      "from_account": "800428D50",
      "to_account": "80051FF00",
      "amount": 990000.0,
      "currency": "US Dollar",
      "timestamp": "2026-06-02T10:14:00",
      "typology_flag": "structuring",
      "xgb_score": 0.94
    },
    {
      "txn_id": "CASE-000042-TXN-90002",
      "from_account": "8004possibly2A1",
      "to_account": "80051FF00",
      "amount": 985000.0,
      "currency": "US Dollar",
      "timestamp": "2026-06-03T11:37:00",
      "typology_flag": "structuring",
      "xgb_score": 0.88
    },
    {
      "txn_id": "CASE-000042-TXN-90003",
      "from_account": "800428D50",
      "to_account": "80051FF00",
      "amount": 992500.0,
      "currency": "US Dollar",
      "timestamp": "2026-06-04T09:05:00",
      "typology_flag": "structuring",
      "xgb_score": 0.91
    }
  ],
  "graph_edges": [
    { "source": "800428D50",      "target": "80051FF00",     "relation": "SENT",       "weight": 0.94 },
    { "source": "8004possibly2A1","target": "80051FF00",     "relation": "SENT",       "weight": 0.88 },
    { "source": "800428D50",      "target": "PAN-AABCX1234F", "relation": "LINKED_PAN", "weight": 1.0 },
    { "source": "8004possibly2A1","target": "PAN-AABCX1234F", "relation": "LINKED_PAN", "weight": 1.0 }
  ],
  "entities": [
    {
      "id": "800428D50", "type": "Account", "name": "A/c 800428D50",
      "owner_pan": "AABCX1234F", "director_of": null,
      "kyc_status": "FAILED", "entity_subtype": "Shell Company",
      "jurisdiction": "High Risk", "linked_company": "Orion Holdings (synthetic)"
    },
    {
      "id": "8004possibly2A1", "type": "Account", "name": "A/c 8004..2A1",
      "owner_pan": "AABCX1234F", "director_of": null,
      "kyc_status": "FAILED", "entity_subtype": "Shell Company",
      "jurisdiction": "High Risk", "linked_company": "Orion Holdings (synthetic)"
    },
    {
      "id": "80051FF00", "type": "Account", "name": "A/c 80051FF00",
      "owner_pan": "AFZPK7190K", "director_of": null,
      "kyc_status": "PENDING", "entity_subtype": "Individual",
      "jurisdiction": "Standard", "linked_company": null
    },
    {
      "id": "PAN-AABCX1234F", "type": "PAN", "name": "AABCX1234F",
      "owner_pan": null, "director_of": null
    }
  ],
  "shared_pan_groups": [
    { "pan": "AABCX1234F", "accounts": ["800428D50", "8004possibly2A1"] }
  ],
  "alert_details": [
    { "account": "800428D50", "alert_type": "structuring",
      "detail": "3 near-threshold transfers to 80051FF00 within 72h, each just under $1,000,000" },
    { "account": "800428D50", "alert_type": "velocity",
      "detail": "6 outbound transactions within a 48h window" }
  ]
}
```

Notes:
- `timestamp` is ISO-8601 **without** timezone (naive) — matches our fixtures and
  the frozen `datetime` field. If you send `Z`/offset it still parses; just be
  consistent so the timeline sorts right.
- `accounts` must equal the set of account ids that appear as `from_account`/
  `to_account` — we use it to fetch documents and to size the case.
- PAN node id convention: **`"PAN-" + pan`**. Our `linked_pan` detector also reads
  `entities[].owner_pan` directly, so even if you skip the PAN node entirely we'll
  still detect the ring from `owner_pan` + `shared_pan_groups`. Sending the PAN
  node just makes the graph view richer.

---

## 5. `GET /cases` — `CaseSummary[]`

```json
[
  { "case_id": "CASE-000042", "risk_band": "RED",    "p": 0.91, "member_count": 3 },
  { "case_id": "CASE-000043", "risk_band": "YELLOW", "p": 0.56, "member_count": 5 }
]
```

`member_count` = `len(member_alert_ids)` (what we render on the dashboard card).
Support `?risk_band=RED` and `?limit=&offset=`; Person 2 currently calls it
plain and with `?threshold=` — see §7.

---

## 6. `GET /metrics/comparison` — `ComparisonMetric[]`

Frontend PR-AUC / comparison chart reads exactly this. Keep `model` to the three
enum values.

```json
[
  { "model": "gemma_probe", "precision": 0.88, "recall": 0.79, "threshold": 0.5 },
  { "model": "xgboost",     "precision": 0.81, "recall": 0.74, "threshold": 0.5 },
  { "model": "rule_count",  "precision": 0.52, "recall": 0.90, "threshold": 0.5 }
]
```

Your `/metrics/comparison/full` (with AUPRC/AUROC) is a welcome extra — the
frontend will show them if present, but the base endpoint must stay this shape.

---

## 7. `POST /risk/threshold`

Request `{"threshold": 0.6}` → response `{"red": 12, "yellow": 30, "green": 108}`.
Powers the dashboard slider. Until this is live, Person 2 recomputes bands
client-side against the assumed cutoffs, so when you wire it, keep the semantics:
threshold is the **RED** cutoff, YELLOW is `threshold - 0.3`, else GREEN (or send
us your exact band math and we'll match it — just tell us which).

---

## 8. Integration-day checklist (mirrors SPEC card 3, made concrete)

1. **Contract diff.** Apply the §3 diff to the root `shared_contracts.py`. Person 1
   and Person 2 both copy it verbatim. Run:
   ```python
   from shared_contracts import Case
   import json
   Case.model_validate(json.load(open("engine/fixtures/hero_cases.json"))[0])
   ```
   on **both** repos. It must pass on both before wiring anything.
2. **Fixture parity.** Person 1 delivers `hero_cases.json` (array of full `Case`).
   Person 2 copies it to `reasoning/fixtures/mock_cases.json`, restarts :8002,
   and confirms `/investigate/{id}` still works end-to-end offline.
3. **Swap the wire.** Person 2 sets `ENGINE_API_URL=http://localhost:8001`. Now
   `/cases*` on :8002 proxies to your engine. One real hero case through the full
   chain via curl:
   `engine /cases/{id}` → `reasoning /evidence/{id}` → `reasoning /investigate/{id}`
   → `reasoning /export/{id}`.
4. **Relationship smoke test.** For each hero case, hit
   `POST http://localhost:8002/evidence/{id}` and confirm `relationships` is
   non-empty and `missing_evidence` is `[]`. If a RED case comes back with a
   missing-relationship gate, your `owner_pan`/`shared_pan_groups`/identity edges
   didn't come through — fix on the engine side, not in reasoning.
5. **Amount grounding.** Confirm the STR's cited amounts render green, not red.
   Red amount bands after integration = the numbers in `transactions[].amount`
   don't match what the model was shown → almost always a rounding or
   units mismatch on the engine side.

---

## 9. What Person 2 does NOT need (so you don't over-build for us)

- We don't need the `is_laundering` ground truth, case labels, or probe training
  internals — never send them.
- We don't need a separate documents/KYC-image endpoint; document evidence is
  stubbed on our side (synthetic vision fixtures). If you happen to expose real
  extracted KYC fields on the entity (`kyc_status`, `entity_subtype`) we'll cite
  them — but that's a bonus, not a dependency.
- We don't need `/cases/{id}/graph` for the current frontend (we build the graph
  from `Case.graph_edges` + `entities` ourselves), but it's fine to keep it.

---

## 10. Single source of truth for the four new models

Paste this block into the root `shared_contracts.py` (Person 2 will mirror it):

```python
class SharedPanGroup(BaseModel):
    pan: str
    accounts: List[str]

class AlertDetail(BaseModel):
    account: str
    alert_type: Literal["velocity", "threshold", "structuring"]
    detail: str

# Transaction: + xgb_score: Optional[float] = None
# Entity:      + kyc_status: Optional[Literal["VERIFIED","PENDING","FAILED"]] = None
#              + entity_subtype: Optional[str] = None
#              + jurisdiction: Optional[str] = None
#              + linked_company: Optional[str] = None
# Case:        + shared_pan_groups: List[SharedPanGroup] = []
#              + alert_details: List[AlertDetail] = []
```

All new fields are optional with defaults → **fully backward compatible**: today's
fixtures and today's Person 2 code keep working the moment this lands, and the
richer engine output flows straight through when it's ready.
```
