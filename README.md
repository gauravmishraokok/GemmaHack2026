# SentinelAI

**Build with Gemma: Bengaluru AI Sprint — Track 2: Gemma Financial Compliance & Risk Triage**

An air-gapped AML co-investigator for small NBFCs and co-operative banks. It clusters raw transactions into investigable cases via graph community detection, reconstructs each case's evidence (timeline, relationships, documents, regulation citations), reasons over that evidence with Gemma under grammar-constrained decoding, and drafts a filing-locked FIU-IND Suspicious Transaction Report whose every sentence is scored by the model's own confidence — without a single byte of KYC data leaving the building.

---

## The problem

Small NBFCs and co-op banks carry a disproportionate compliance burden under steep per-day penalties, yet cloud AML tools are off the table because customer data legally cannot leave their premises (RBI localization + DPDP). Rule-based AML systems generate 90%+ false positives. SentinelAI replaces rigid rules with a tunable, learned risk boundary that still emits a rule-legible audit trail — running entirely on-prem.

## Why Gemma, specifically

Gemma runs entirely on-device, and SentinelAI exploits what only local weights allow:

- **Suspicion scoring reads Gemma's internal activations** through a trained linear probe (not a prompt), giving a calibrated, tunable decision boundary that attacks AML's false-positive problem directly.
- **The STR is produced under GBNF grammar-constrained decoding**, so the filing physically cannot contain an invalid FIU Ground-of-Suspicion tag or a hallucinated figure — the grammar makes the conclusion tokens unreachable until the evidence array has closed.
- **Every narration sentence is scored by Gemma's own token-level logprobs** into a confidence heat-map, so the analyst sees exactly which claims to verify before attesting.

None of activation probing, logit-masked decoding, or per-token confidence is possible against a cloud API, which exposes only text. Cloud AI is also legally out of scope here — Gemma isn't a convenience, it's the only architecture that is both compliant and instrumentable.

## Architecture

```
DATA INGESTION
SAML-D txns · synthetic KYC/PAN/GST · invoices · prior alerts · PMLA/RBI text
                              │
╔══════════════════════════════▼══════════════════════════════════════╗
║  LAYER 1 — PREPROCESSING            [BATCH PLANE — engine, :8001]   ║
╠═══════════════════════════════════════════════════════════════════════╣
║  ① Rule Engine        velocity / threshold / structuring-proximity    ║
║  ② Graph Builder      networkx — SENT / OWNED_BY / DIRECTOR_OF /      ║
║                        LINKED_PAN                                     ║
║  ③ Community Detection  Louvain — 500 alerts → 5 cases                ║
║  ④ Risk Prioritization  Gemma Activation Probe (primary) vs.          ║
║                          XGBoost / rule-count (baselines)             ║
║  ⑤ Postgres  cases · case_members · transactions · audit_log          ║
╚═══════════════════════════════════════════════════════════════════════╝
                              │  analyst clicks Case #42
╔══════════════════════════════▼══════════════════════════════════════╗
║  LAYER 2 — EVIDENCE CONSTRUCTION   [INTERACTIVE PLANE — reasoning, :8002]║
╠═══════════════════════════════════════════════════════════════════════╣
║  Timeline · Relationships (graph) · Documents (Gemma vision, stubbed  ║
║  for demo speed) · Regulations (local RAG over PMLA/RBI/FIU-IND)      ║
║  ⑥ EVIDENCE VALIDATOR — hard gate: missing critical evidence → STOP   ║
╚═══════════════════════════════════════════════════════════════════════╝
                              │
╔══════════════════════════════▼══════════════════════════════════════╗
║  LAYER 3 — GEMMA REASONING (generates UNDER grammar)                  ║
╠═══════════════════════════════════════════════════════════════════════╣
║  Evidence-first prompt (6 steps) → GBNF grammar structurally enforces ║
║  evidence → pattern → conclusion → gos_tag → narration, in that order ║
╚═══════════════════════════════════════════════════════════════════════╝
                              │
╔══════════════════════════════▼══════════════════════════════════════╗
║  LAYER 4 — TRUST                                                       ║
╠═══════════════════════════════════════════════════════════════════════╣
║  ⑦ Confidence heat-map (logprobs → sentence bands)                    ║
║  ⑧ Human review — model drafts, human attests                          ║
║  ⑨ Export — FIU XML + immutable audit log                             ║
╚═══════════════════════════════════════════════════════════════════════╝
                              │
╔══════════════════════════════▼══════════════════════════════════════╗
║  FRONTEND (React) — Dashboard 🔴🟡🟢 + threshold slider → Case view:  ║
║  Timeline · Graph · Evidence · Investigation · STR + Heatmap          ║
╚═══════════════════════════════════════════════════════════════════════╝
```

## Why not the obvious alternatives

| Objection | Answer |
|---|---|
| Why not cloud AI? | RBI localization + DPDP make it non-compliant for this data, and the self-audit layer (activation probe, logprobs) is architecturally impossible on an API that only returns text. |
| Why not a rule engine? | Rule engines are the 90%-false-positive problem. SentinelAI replaces rigidity with a tunable learned boundary that still emits a rule-legible audit trail. |
| Why not a big model + faithfulness judge? | That's the black-box workaround teams use when they lack model weights. This is cheaper (single pass, no re-sampling), more principled (real logits, not a second model guessing), and runs on-prem. |
| How do you cluster millions of rows? | Not with the LLM — Louvain/Leiden community detection on the transaction graph does that, with published accuracy. |
| Will the LLM hallucinate figures into a legal filing? | The grammar locks the fields, amounts are copied from verified transactions rather than freely generated, and the heat-map flags any shaky narration before a human attests. |

## Team & repo split

Built in parallel across two tracks (see `01_SPEC_person1_data_intelligence_engine.md` and `02_SPEC_person2_reasoning_evidence_product.md`), merged per `03_SPEC_integration_and_merge.md`:

- **Person 1 — Data & Intelligence Engine** (`engine/`, port 8001): ingestion, rule engine, graph + Louvain clustering, Gemma activation probe risk scoring, baselines, Postgres, case API.
- **Person 2 — Reasoning, Evidence & Product** (`reasoning/` + `frontend/`, port 8002): Gemma serving under GBNF grammar, evidence construction (timeline/relationships/documents/regulations), confidence heat-map, STR drafting, full React dashboard.
- Both import a single frozen `shared_contracts.py` so the two tracks never block each other and merge cleanly.

## Tech stack

Python (`fastapi`, `pandas`, `networkx`, `transformers`, `scikit-learn`, `xgboost`, `sqlalchemy`), Gemma 3 4B served two ways (`transformers` for activation probing, `llama.cpp`/`llama-cpp-python` for grammar-constrained generation + logprobs), `chromadb` + `sentence-transformers` for regulation retrieval, React + Vite + Tailwind + `recharts` for the frontend, Postgres (or SQLite as a time-boxed fallback).

## Running it

```bash
# 1. Engine (port 8001)
cd engine && uvicorn api.main:app --port 8001 --reload

# 2. Reasoning (port 8002) — needs Ollama running with gemma4:12b + nomic-embed-text pulled
cd reasoning && uvicorn api.main:app --port 8002 --reload

# 3. Frontend
cd frontend && npm install && npm run dev
```

Frontend reads `VITE_REASONING_URL` (default `http://localhost:8002`). On integration day set `ENGINE_API_URL=http://localhost:8001` for the reasoning service — it proxies cases from the engine and nothing else changes (see `change.md` for Person 2's implementation notes and deviations).

## Dataset

[SAML-D — Anti Money Laundering Transaction Data](https://www.kaggle.com/) (Kaggle). All identity data (PAN, director/company relationships, KYC metadata) beyond raw transactions is synthetically generated, per the hackathon's data policy — no real personal data is used.

## Demo script

Paste a SAML-D batch → dashboard collapses hundreds of alerts to 5 cases → open a case → timeline, graph, and evidence self-assemble → Gemma suggests next investigative questions and cites the relevant PMLA section → a grammar-valid STR drafts → sentences light up green/red by the model's own confidence → analyst clicks attest → FIU-IND XML exports. Seven capabilities, one air-gapped forward pass.

## Evaluation rubric mapping

| Criterion | Weight | Where SentinelAI addresses it |
|---|---|---|
| Gemma Integration | 30% | Activation probing (not prompting) for risk scoring, GBNF grammar-constrained decoding for the STR, native token logprobs for confidence — none possible on a cloud API. |
| Innovation & Impact | 30% | Turns hundreds of noisy alerts into a handful of investigable cases; turns hours of STR drafting into a verify-and-attest step; targets a real, underserved segment (small NBFCs/co-ops) with a real legal constraint (data localization). |
| Functionality | 20% | End-to-end working pipeline: ingestion → clustering → risk scoring → evidence → grammar-constrained generation → confidence → export. |
| Presentation & Write-up | 20% | This README + the Kaggle write-up form answers below. |

## Submission form answers

**Track Selection:** Track 2 — Gemma Financial Compliance & Risk Triage.

**AI & Gemma Usage:** Gemma runs entirely on-device, and SentinelAI exploits what only local weights allow. Suspicion scoring reads Gemma's internal activations through a trained linear probe (not a prompt), giving a calibrated, tunable decision boundary that attacks AML's 90%+ false-positive problem. The STR is produced under GBNF grammar-constrained decoding, so the filing physically cannot contain an invalid FIU Ground-of-Suspicion tag or a hallucinated figure. Each narration sentence is scored by Gemma's own token-level logprobs into a confidence heat-map, so the analyst sees exactly which claims to verify before attesting. None of these — activation probing, logit-masked decoding, per-token confidence — is possible against a cloud API, which exposes only text. Cloud AI is also legally impossible here: RBI bars KYC data from third-party servers. Gemma isn't a convenience; it's the only architecture that is both compliant and instrumentable.

**Project Idea:** Small NBFCs and co-op banks carry a 3–5× compliance burden under ₹10 lakh/day penalties, yet cloud AML tools are off-limits because customer data can't leave their premises. SentinelAI is an air-gapped co-investigator that clusters raw transactions into connected cases via graph community detection, reconstructs each case's timeline and entity graph, reads scanned evidence with Gemma's vision tower, suggests investigative next steps, cites the relevant PMLA/RBI provision, and drafts a filing-locked FIU-IND STR whose every sentence is heat-mapped by the model's own confidence. Target users: compliance/MLRO teams at India's small reporting entities. Impact: turns hundreds of noisy alerts into a handful of investigable cases, and turns hours of STR drafting into a verify-and-attest step — without a single byte leaving the building.

## Known limitations / roadmap

- Document/vision extraction is stubbed with synthetic fixtures for demo reliability; a full Gemma-vision pipeline over real scanned documents is the natural next step.
- Regulation retrieval covers a curated subset of PMLA/RBI/FIU-IND text, not the full corpus.
- The activation probe is trained on SAML-D's labeled typologies; production deployment would need retraining on an institution's own historical STR/CTR outcomes.
