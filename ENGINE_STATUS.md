# viGEMMAlya — Engine (Person 1) Status Document

> **Date:** 2026-07-18  
> **Branch:** main  
> **Author:** Person 1 (Data & Intelligence Engine)

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [What Is Done](#2-what-is-done)
3. [How It Works — Architecture](#3-how-it-works--architecture)
4. [Current Implementation (File-by-File)](#4-current-implementation-file-by-file)
5. [Data Pipeline Phases](#5-data-pipeline-phases)
6. [API Endpoints](#6-api-endpoints)
7. [Known Issues & Open Problems](#7-known-issues--open-problems)
8. [What Is Left To Do](#8-what-is-left-to-do)
9. [Notes for Person 2](#9-notes-for-person-2)
10. [Integration Guide](#10-integration-guide)

---

## 1. System Overview

viGEMMAlya is an Anti-Money Laundering (AML) detection system split into two services:

| Service | Port | Responsibility |
|---------|------|----------------|
| **Person 1** — Engine | `8001` | Data ingestion, rule engine, graph clustering, ML risk scoring, DB persistence |
| **Person 2** — Reasoning | `8002` | Evidence packing, Gemma narrative generation, STR draft, investigation results |

Person 1 is the **sole source of truth** for structured case data. Person 2 **reads from Person 1's API** — it does not have its own database.

The two services share a single Pydantic v2 contract file: [`shared_contracts.py`](shared_contracts.py).

---

## 2. What Is Done

### Data & Ingestion
- [x] IBM AML CSV loader (`engine/ingestion/load_saml_d.py`) — handles duplicate "Account"/"Account.1" columns, stratified sampling by `is_laundering`, full column rename map
- [x] Synthetic identity injector (`engine/ingestion/synth_identity.py`) — generates Person/Company/PAN entities for accounts, hero group handling

### Rule Engine
- [x] Velocity rule — flags accounts with >5 transactions in a 48-hour sliding window
- [x] Threshold rule — flags transactions near reporting thresholds (₹47k–₹50k, ₹95k–₹1L, ₹2.4L–₹2.5L)
- [x] Structuring rule — flags repeated near-threshold pairs between same sender/receiver

### Graph & Clustering
- [x] NetworkX `MultiDiGraph` builder — SENT, OWNED_BY, DIRECTOR_OF, LINKED_PAN edge types
- [x] 2-hop subgraph expansion from flagged accounts
- [x] Louvain community detection (`seed=42`) via `python-louvain`
- [x] Community-to-case assembler (each community becomes one `Case`)

### ML Risk Scoring
- [x] **XGBoost baseline** — transaction-level features (17 features), trained on 5,078,345 IBM AML transactions via Kaggle. AUROC=0.934 on held-out test set. Case-level score = `max*0.6 + mean*0.3 + frac_high_risk*0.1`
- [x] **Gemma probe** — `google/gemma-3-1b-it`, mid-layer hidden states, mean-pooled, bfloat16. PCA(64) + LogisticRegressionCV with StratifiedKFold inner CV. Falls back to TF-IDF when Gemma loading fails (segfault issue — see §7)
- [x] Mahalanobis OOD distance in PCA space
- [x] Model comparison metrics (AUPRC/AUROC) stored in DB

### Persistence & API
- [x] SQLAlchemy ORM + SQLite (`engine/data/engine.db`) with FK indexes, joinedload to avoid N+1
- [x] FastAPI on port 8001 with 6 endpoints + CORS
- [x] `hero_cases.json` written at end of seed (top RED cases + 1 GREEN for fixture diversity)
- [x] Seed pipeline runs end-to-end clean on Windows

### Kaggle Training
- [x] Kaggle training script (`engine/notebooks/kaggle_train_xgb.py`) — complete, self-contained
- [x] Pretrained model files present: `engine/data/xgb_pretrained.json` (476 KB) + `engine/data/xgb_pretrained_meta.json`

---

## 3. How It Works — Architecture

```
IBM AML CSV (HI-Small_Trans.csv, 5M rows)
         │
         ▼
[Phase A] load_saml_d.py  ──► DataFrame (sender_account, receiver_account, amount,
                                          payment_type, payment_currency, is_laundering, ...)
         │
         ▼
[Phase B] Rule Engine     ──► alerts DataFrame (account, alert_type)
   velocity / threshold / structuring
         │
         ▼
[Phase C/D] Synthetic identity injection  ──► identity_map {account -> {pan, director_of, ...}}
         │
         ▼
[Phase E] Graph (NetworkX MultiDiGraph)
          Louvain clustering             ──► communities (list of account sets)
          communities_to_cases()         ──► raw_cases (list of dicts with transactions DF)
         │
         ▼
[Phase G] GemmaProbe.fit_with_split()
          or GemmaProbe.load()           ──► probe (fitted PCA + LR)
         │
         ▼
[Phase H] XGBBaseline.load_pretrained()
          (or fit_on_transactions / load) ──► xgb (fitted XGBClassifier)
         │
         ▼
[Phase I] compute_comparison()           ──► comparison_data [{model, precision, recall, ...}]
         │
         ▼
[Phase J] SQLite DB persistence
          CaseModel, TransactionModel, GraphEdgeModel, EntityModel, ComparisonMetricModel
         │
         ▼
[Phase K] hero_cases.json               ──► engine/fixtures/hero_cases.json
         │
         ▼
FastAPI (port 8001)                      ──► Person 2 reads via HTTP
```

### Key Design Decisions

| Decision | Reason |
|----------|---------|
| XGBoost at transaction level, not case level | Cases have wildly different sizes; transaction features are consistent and matchable to the Kaggle training distribution |
| Kaggle pretrained model always takes priority over `--force` local training | 5M row trained AUROC=0.934 vs. local sample of ≤50k — no comparison |
| `import torch` FIRST before numpy in seed.py | Windows MKL DLL conflict: numpy loads Intel MKL, then torch can't load its own DLL versions. Importing torch first prevents this |
| txn_id prefixed with case_id | Same physical transaction can appear in multiple Louvain communities; bare txn_id causes UNIQUE constraint violation in SQLite |
| TF-IDF fallback for probe | Gemma 1B segfaults during checkpoint loading (likely corrupted HF cache from earlier 4B attempt). TF-IDF keeps the pipeline running end-to-end |
| Gemma 1B (not 4B) | 4B float32 requires ~16 GB RAM; machine has ~7.2 GB available. 1B bfloat16 needs ~2 GB |
| Native XGBoost JSON export (not pickle) | Pickle encodes class path — `XGBClassifier` must be importable at load site. JSON format is class-path-free and loads cleanly with `model.load_model()` |

---

## 4. Current Implementation (File-by-File)

### `shared_contracts.py` (project root)
Pydantic v2 models shared between Person 1 and Person 2. **Do not modify without coordinating with Person 2.**

Key models:
- `Transaction` — `txn_id`, `from_account`, `to_account`, `amount`, `currency`, `timestamp`, `typology_flag`
- `GraphEdge` — `source`, `target`, `relation` (one of `SENT|OWNED_BY|DIRECTOR_OF|LINKED_PAN`), `weight`
- `Entity` — `id`, `type` (one of `Account|Person|Company|PAN`), `name`, `owner_pan`, `director_of`
- `RiskScore` — `p` (probability 0-1), `margin` (LR margin), `ood` (Mahalanobis OOD distance)
- `Case` — aggregates all of the above, plus `risk_band` (`RED|YELLOW|GREEN`), `accounts`, `member_alert_ids`
- `CaseSummary` — lightweight list view: `case_id`, `risk_band`, `p`, `member_count`
- `ComparisonMetric` — `model`, `precision`, `recall`, `threshold`
- `EvidencePack`, `STRDraft`, `InvestigationResult` — consumed by Person 2, not written by Person 1

### `engine/ingestion/load_saml_d.py`
Loads the IBM AML CSV. Critical: pandas auto-renames the duplicate "Account" column to "Account.1" — handled explicitly. Stratified sampling preserves laundering ratio when `sample_n` is set.

### `engine/ingestion/synth_identity.py`
Generates synthetic PAN numbers, Person entities, Company entities. Hero groups (known laundering accounts) get richer synthetic profiles for demo purposes.

### `engine/rules/velocity.py`, `threshold.py`, `structuring.py`
Each returns a DataFrame with columns `["account", "alert_type"]`. All three are concatenated in Phase B after checking for non-empty list (fixes `ValueError: No objects to concatenate` when the sample is too small to trigger any rule).

### `engine/graph/build_graph.py`
Builds the MultiDiGraph. SENT edges from transaction data, identity edges from `identity_map`.

### `engine/graph/cluster.py`
Louvain clustering → `detect_communities()` returns `List[Set[str]]` (account sets). `communities_to_cases()` joins back transaction data for each community.

### `engine/risk/baselines.py`

Key constants:
```python
MODELS_DIR    = os.path.join(os.path.dirname(__file__), "..", "data")
XGB_PATH      = os.path.join(MODELS_DIR, "xgb_model.pkl")
XGB_JSON_PATH = os.path.join(MODELS_DIR, "xgb_pretrained.json")   # ← Kaggle model
XGB_META_PATH = os.path.join(MODELS_DIR, "xgb_pretrained_meta.json")
```

Key methods:
- `XGBBaseline._txn_features(row)` — extracts 17 features from a single transaction row
- `XGBBaseline.fit_on_transactions(df)` — trains on raw transaction DataFrame
- `XGBBaseline.predict_case(raw_case)` — returns case-level score: `max*0.6 + mean*0.3 + frac_high_risk*0.1`
- `XGBBaseline.load_pretrained()` — loads Kaggle JSON model; sets `_p75`, `_p95` from meta JSON
- `XGBBaseline.is_trained()` — True if either `.pkl` or JSON pair exist
- `rule_count_score(raw_case)` — simple normalized count of rule alerts, used as a third comparison baseline

Currency and payment type maps cover: IBM AML full names ("US Dollar", "Wire", "Reinvestment"), their uppercase variants (what `.str.upper()` produces), and ISO codes (USD, EUR, etc.) for synthetic data.

### `engine/risk/probe.py`

- `GEMMA_MODEL_ID = "google/gemma-3-1b-it"`
- `USE_GEMMA = os.environ.get("USE_GEMMA", "1") == "1"` — set to `"0"` to force TF-IDF
- `_extract_gemma_activations()` — loads Gemma, runs forward pass with `output_hidden_states=True` (at forward call, NOT in `from_pretrained()`), takes mean pool of mid-layer hidden state
- `_fit_model()` — falls back to `LogisticRegression(C=0.01)` when fewer than 4 positive cases (otherwise StratifiedKFold CV fails with 1-member class warning)
- `GemmaProbe.predict(raw_case)` returns `(p, margin, ood)` tuple

### `engine/risk/compare.py`
Uses only public API (no private imports):
```python
probe_probs = np.array([probe.predict(c)[0] for c in eval_cases])
xgb_probs   = np.array([xgb.predict_case(c) for c in eval_cases])
rc_probs    = np.array([rule_count_score(c) for c in eval_cases])
```

Returns list of dicts with `model`, `precision`, `recall`, `threshold`, `auprc`, `auroc`.

### `engine/db/models.py`
SQLAlchemy ORM. Tables: `cases`, `transactions`, `graph_edges`, `entities`, `comparison_metrics`, `audit_log`. `DATABASE_URL` defaults to SQLite but can be overridden via env var for Postgres.

### `engine/db/seed.py`
The master pipeline orchestrator. **Import order matters:** `torch` must be imported before `numpy` — do not change this.

Phases A→K as described in §5. The `run_seed(force, sample_n)` function is callable programmatically (used by FastAPI startup event if DB is empty).

### `engine/api/main.py`
FastAPI app on port 8001. On startup, auto-runs seed if DB is empty. Uses `joinedload` for all relationship eager loading.

### `engine/notebooks/kaggle_train_xgb.py`
Self-contained Kaggle training script. Paste into a Kaggle notebook code cell. Output: `xgb_pretrained.json` + `xgb_pretrained_meta.json`.

### `engine/fixtures/hero_cases.json`
Written by Phase K of seed. Top 4 RED + 1 GREEN case. This is the primary fixture for Person 2 development and testing.

### `engine/data/`
- `engine.db` — SQLite database
- `xgb_pretrained.json` — 476 KB, Kaggle-trained XGBoost (DO NOT delete)
- `xgb_pretrained_meta.json` — p75: 12297.84, p95: 623757.22, AUPRC=0.046, AUROC=0.934
- `xgb_model.pkl` — local-trained fallback (much weaker; ignored when JSON files present)
- `gemma_probe.pkl` — serialized GemmaProbe (PCA + LR); may not exist if Gemma segfaulted

---

## 5. Data Pipeline Phases

| Phase | Name | Status | Notes |
|-------|------|--------|-------|
| A | Load transactions | ✅ Working | IBM AML or synthetic CSV |
| B | Rule engine | ✅ Working | Empty-concat guard added |
| C | Hero group identification | ✅ Working | Uses `is_laundering` column |
| D | Synthetic identity injection | ✅ Working | |
| E | Graph + Louvain clustering | ✅ Working | |
| F | Case labeling | ✅ Working | |
| G | Gemma probe training/loading | ⚠️ Fallback | Gemma 1B segfaults on this machine → TF-IDF fallback active |
| H | XGBoost training/loading | ✅ Working | Kaggle pretrained model loads cleanly |
| I | Comparison metrics | ✅ Working | |
| J | DB persistence | ✅ Working | |
| K | hero_cases.json output | ✅ Working | |

---

## 6. API Endpoints

Base URL: `http://localhost:8001`

| Method | Path | Response | Notes |
|--------|------|----------|-------|
| GET | `/health` | `{"status": "ok"}` | |
| GET | `/cases` | `List[CaseSummary]` | Optional `?risk_band=RED&limit=50` |
| GET | `/cases/{case_id}` | `Case` | Full case with transactions, edges, entities |
| GET | `/cases/{case_id}/graph` | `{entities, edges}` | Same data, graph-view shape |
| POST | `/risk/threshold` | `{red, yellow, green}` | Recomputes risk bands with new threshold; body: `{"threshold": 0.6}` |
| GET | `/metrics/comparison` | `List[ComparisonMetric]` | Standard contract fields |
| GET | `/metrics/comparison/full` | extended dict | Adds `auprc`, `auroc` fields not in shared contract |

**To start:** `uvicorn engine.api.main:app --port 8001 --reload`

---

## 7. Known Issues & Open Problems

### Issue 1: Gemma 1B Segfault (CRITICAL — Probe falls back to TF-IDF)

**Symptom:** Python exits with segfault (exit code 139) when loading `google/gemma-3-1b-it` checkpoint shards.

**Root cause:** Likely corrupted HF cache from an earlier aborted download of `google/gemma-3-4b-it` (which OOM-killed). The 4B segfault may have left partial/corrupt files that conflict with the 1B model loading.

**Current state:** Pipeline falls back to TF-IDF probe automatically. All other phases are unaffected.

**Fix to try:**
```powershell
# Delete the corrupted cache
Remove-Item -Recurse -Force "$env:USERPROFILE\.cache\huggingface\hub\models--google--gemma-3-4b-it"
Remove-Item -Recurse -Force "$env:USERPROFILE\.cache\huggingface\hub\models--google--gemma-3-1b-it"
# Then re-download only 1B:
$env:TRANSFORMERS_CACHE = "$env:USERPROFILE\.cache\huggingface\hub"
$env:HF_TOKEN = "<your-token>"
python -c "from transformers import AutoModelForCausalLM; AutoModelForCausalLM.from_pretrained('google/gemma-3-1b-it', token='<your-token>')"
```

**Workaround:** Run with `USE_GEMMA=0` env var — seeds cleanly with TF-IDF, Kaggle XGBoost still active.

### Issue 2: Low Positive Case Ratio

**Symptom:** With IBM AML's 0.1019% laundering rate, a 50k sample yields roughly 50 laundering transactions → after Louvain clustering, only ~5-10 positive cases out of ~150-200 total.

**Impact:** Probe's LogisticRegressionCV falls back to fixed-C LR (LogisticRegression(C=0.01)). The probe operates in an underfitted regime and its precision/recall are poor.

**Fix:** Use `--sample 500000` or all rows (requires ~8 GB RAM). With 500k rows, you get ~500 laundering transactions → ~20-50 positive cases → proper CV.

**Note:** XGBoost is unaffected because it trains at transaction level on the full Kaggle dataset.

### Issue 3: Windows DLL Conflict (torch/numpy)

**Status:** FIXED. `import torch` is the first import in `seed.py`. Do not move it.

**If it breaks again:** The symptom is `[WinError 1114] A dynamic link library (DLL) initialization routine failed` on `torch\lib\c10.dll`. The fix is ensuring torch is imported before numpy in any entry-point script.

### Issue 4: `use_label_encoder` Warning

XGBoost 2.x removed the `use_label_encoder` parameter. Removed from our code. If you see this warning from an old saved `.pkl` model, delete `engine/data/xgb_model.pkl` and let the Kaggle JSON model load instead.

---

## 8. What Is Left To Do

### High Priority
- [ ] **Fix Gemma 1B segfault** — delete corrupted HF cache, re-download cleanly (see §7 Issue 1)
- [ ] **Live API endpoint testing** — run `uvicorn engine.api.main:app --port 8001` and verify all 6 endpoints respond with correct shapes against the live DB
- [ ] **Verify hero_cases.json** — confirm the JSON validates against `shared_contracts.py` `Case` model before handing off to Person 2

### Medium Priority
- [ ] **Larger sample run** — `python -m engine.db.seed --sample 500000` for better probe training (requires ~8 GB RAM free)
- [ ] **Gemma probe quality check** — once Gemma loads cleanly, compare probe AUPRC against TF-IDF fallback
- [ ] **Postgres migration** — swap `DATABASE_URL` env var for a real Postgres instance for production

### Low Priority
- [ ] **`/cases/{case_id}/graph` endpoint** — verify the graph shape satisfies Person 2's visualization requirements
- [ ] **`POST /risk/threshold`** — test that band recomputation persists correctly across API restarts
- [ ] **Audit log** — `AuditLogModel` is defined in DB but not written anywhere in the seed pipeline

---

## 9. Notes for Person 2

### What You're Getting

Person 1 exposes a live HTTP API at `http://localhost:8001`. You should never touch the SQLite DB directly — use the API.

### `hero_cases.json` Location

```
engine/fixtures/hero_cases.json
```

This is the **primary development fixture** — 5 fully populated cases (4 RED + 1 GREEN) with all transactions, graph edges, and entities. Load this for offline development when you don't want to depend on the running API.

### Case Object Shape

Every `Case` from `/cases/{case_id}` or `hero_cases.json` has this structure:

```json
{
  "case_id": "CASE-abc123",
  "risk": {"p": 0.82, "margin": 0.41, "ood": 1.23},
  "risk_band": "RED",
  "member_alert_ids": ["alert-1", "alert-2"],
  "accounts": ["8000000001", "8000000002"],
  "transactions": [
    {
      "txn_id": "CASE-abc123_TXN-456",
      "from_account": "8000000001",
      "to_account": "8000000002",
      "amount": 49500.0,
      "currency": "US Dollar",
      "timestamp": "2022-09-01T10:23:00",
      "typology_flag": null
    }
  ],
  "graph_edges": [
    {"source": "8000000001", "target": "8000000002", "relation": "SENT", "weight": 3}
  ],
  "entities": [
    {"id": "8000000001", "type": "Account", "name": "SYNTH-Person-001", "owner_pan": "SYNTH-PAN-001", "director_of": null}
  ]
}
```

### Important: Currency Field

`transaction.currency` contains IBM AML **full names** like `"US Dollar"`, `"Euro"`, `"UK Pound"` — NOT ISO codes like `"USD"`. Your narrative templates should handle this. The `CaseSummary.currency` field is whatever the source dataset uses.

### `txn_id` Format

Transaction IDs are prefixed with `case_id`: `"{case_id}_{original_txn_id}"`. This was necessary to prevent UNIQUE constraint violations when the same transaction appears in multiple Louvain communities. Do not strip the prefix — use the full txn_id as the transaction identifier.

### `risk.p` Interpretation

- `p >= 0.7` → RED (high risk, likely laundering)
- `0.4 <= p < 0.7` → YELLOW (suspicious, needs investigation)
- `p < 0.4` → GREEN (clean)

The `risk.margin` is the LR decision margin (positive = more confident). The `risk.ood` is the Mahalanobis OOD distance — high values mean the case is far from the training distribution (less reliable prediction).

### Person 2's Expected Outputs (from `shared_contracts.py`)

Person 2 should produce:
- `EvidencePack` — structured evidence with citations
- `STRDraft` — Suspicious Transaction Report draft
- `InvestigationResult` — final investigation output

These are defined in `shared_contracts.py` but NOT produced or stored by Person 1.

### API Base URL for Development

`http://localhost:8001` — Person 1 must be running before Person 2 can fetch live data.

### Shared Contracts Warning

`shared_contracts.py` is at the project root, imported by both services. Any change to a model must be backward-compatible or coordinated between both persons.

---

## 10. Integration Guide

### Starting Person 1 (Engine)

```powershell
# 1. Activate environment (if using venv)
# 2. Seed the database (first time or after data change):
python -m engine.db.seed --sample 50000

# With Gemma disabled (faster, TF-IDF probe):
$env:USE_GEMMA="0"; python -m engine.db.seed --sample 50000

# Force re-train all models:
python -m engine.db.seed --force --sample 50000

# 3. Start the API:
uvicorn engine.api.main:app --port 8001 --reload
```

### Running the Kaggle XGBoost Training (One-Time Setup)

Only needed if `engine/data/xgb_pretrained.json` is missing.

1. Go to [kaggle.com](https://www.kaggle.com) → New Notebook
2. Add dataset: `ealtman2019/ibm-transactions-for-anti-money-laundering-aml`
3. Paste `engine/notebooks/kaggle_train_xgb.py` into Code cell
4. Run all cells (~5-8 min on CPU)
5. Download `xgb_pretrained.json` and `xgb_pretrained_meta.json` from Output tab
6. Place in `engine/data/`

### Environment Variables

| Variable | Default | Effect |
|----------|---------|--------|
| `USE_GEMMA` | `"1"` | Set to `"0"` to skip Gemma and use TF-IDF probe |
| `DATABASE_URL` | SQLite at `engine/data/engine.db` | Override for Postgres |
| `HF_TOKEN` | (none) | Hugging Face token for Gemma download |

### Quick Sanity Check

```powershell
# After seeding and starting API:
curl http://localhost:8001/health
curl "http://localhost:8001/cases?limit=5"
curl http://localhost:8001/metrics/comparison
```

### Key Files Summary

```
F:\Code\gemdu\
├── shared_contracts.py              # Pydantic v2 shared models (Person 1 + Person 2)
├── ENGINE_STATUS.md                 # This document
├── engine/
│   ├── api/
│   │   └── main.py                 # FastAPI app, port 8001
│   ├── data/
│   │   ├── engine.db               # SQLite database
│   │   ├── xgb_pretrained.json     # Kaggle-trained XGBoost (DO NOT DELETE)
│   │   └── xgb_pretrained_meta.json
│   ├── db/
│   │   ├── models.py               # SQLAlchemy ORM models
│   │   └── seed.py                 # Master pipeline (Phases A-K)
│   ├── fixtures/
│   │   └── hero_cases.json         # 5 demo cases for Person 2
│   ├── graph/
│   │   ├── build_graph.py          # NetworkX graph builder
│   │   └── cluster.py              # Louvain community detection
│   ├── ingestion/
│   │   ├── load_saml_d.py          # IBM AML CSV loader
│   │   └── synth_identity.py       # Synthetic identity generator
│   ├── notebooks/
│   │   └── kaggle_train_xgb.py     # Kaggle training script (paste into Kaggle notebook)
│   ├── risk/
│   │   ├── baselines.py            # XGBoost + rule_count_score
│   │   ├── compare.py              # Model comparison metrics
│   │   └── probe.py                # Gemma probe + TF-IDF fallback
│   └── rules/
│       ├── velocity.py
│       ├── threshold.py
│       └── structuring.py
```

---

*Last updated: 2026-07-18 — Engine pipeline is end-to-end functional with TF-IDF probe + Kaggle XGBoost.*
