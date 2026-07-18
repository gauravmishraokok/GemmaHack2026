# SentinelAI — Project Writeup

**Build with Gemma: Bengaluru AI Sprint — Track 2: Gemma Financial Compliance & Risk Triage**

An air-gapped AML co-investigator for small NBFCs and co-operative banks. It clusters raw transactions into investigable cases via graph community detection, reconstructs each case's evidence (timeline, relationships, KYC, regulation citations), reasons over that evidence with Gemma under schema-constrained decoding, and drafts a filing-ready FIU-IND Suspicious Transaction Report whose every sentence is scored by the model's own confidence — without a single byte of customer data leaving the building.

Built across two parallel tracks — **Person 1: Data & Intelligence Engine** (batch/static plane, port 8001) and **Person 2: Reasoning, Evidence & Product** (interactive/dynamic plane + frontend, port 8002) — merged into one working system.

---

## 🎯 Inspiration

**What local problem are you solving today?**

Small NBFCs and co-operative banks in India carry a disproportionate anti-money-laundering compliance burden. Under India's PMLA (Prevention of Money Laundering Act) and RBI regulations, every reporting entity — regardless of size — must file Suspicious Transaction Reports (STRs) with FIU-IND within 7 working days of forming a suspicion, under steep per-day penalties for non-compliance. Large banks solve this with dedicated compliance teams and expensive AML software; a small co-operative bank or NBFC typically cannot afford either.

Two structural constraints make this worse, not better, for smaller institutions:

- **Rule-based AML systems generate 90%+ false positives.** A rigid rule engine (flag anything over ₹10 lakh, flag anything from a "high-risk" jurisdiction) buries a small compliance team in noise, and every alert still requires a human to manually reconstruct the transaction history, entity relationships, and applicable regulation before they can even decide if it's worth investigating.
- **Cloud AI is legally off the table.** RBI's data localization rules and India's DPDP Act mean customer KYC and transaction data legally cannot leave the institution's premises to reach a third-party cloud API. This rules out ChatGPT-style AML copilots outright for this segment — not as a preference, but as a compliance requirement.

The result: small reporting entities are stuck choosing between a rule engine that drowns them in false positives, or a manual process that doesn't scale. SentinelAI targets exactly this gap — a **fully on-premise, air-gapped co-investigator** that turns hundreds of raw transaction alerts into a handful of investigable cases, reconstructs the evidence around each one automatically, and drafts a legally-structured STR with every claim traceable back to source data — running entirely on hardware the institution already owns, with nothing sent to the cloud.

---

## 🛠️ How We Built It

### Which Gemma model did we use?

Two different Gemma checkpoints, deliberately split across two different jobs because they need two different capabilities from the model:

| Component | Model | Why this one |
|---|---|---|
| **Risk-scoring activation probe** (engine, Person 1) | `google/gemma-3-1b-it` via `transformers`, bfloat16 | Needs raw hidden-state access (`output_hidden_states=True`) for activation probing — this is only possible with the full model weights loaded locally, never through an API. The 4B variant was tried first and rejected: it needs 16GB+ RAM and segfaulted under the available memory budget, so the 1B model was substituted — documented as a deliberate hardware trade-off, not an oversight. |
| **Investigation reasoning + STR drafting** (reasoning, Person 2) | `gemma4:latest` (4B) via **Ollama**, with `gemma4:12b` available as a drop-in upgrade | Needs schema-constrained generation and per-token logprobs in a single pass — Ollama's OpenAI-compatible endpoint provides both. The 4B build completes a full investigation in ~60–80 seconds; the 12B build produces the same quality of output but partially offloads to CPU on our dev hardware and takes 10+ minutes per case — too slow to demo live, so 4B is the default with 12B as a config-flag upgrade path (`OLLAMA_BASE_MODEL=gemma4:12b`) for a machine with more VRAM. |

### Did we use RAG, prompt engineering, or fine-tuning?

**Prompt engineering (evidence-first, 6-step structured prompt) + schema-constrained decoding**, plus a **lightweight local RAG** for regulation citations. No fine-tuning was used — deliberately: see the Challenges section for the reasoning behind that call.

- **Structured, evidence-first prompting.** The reasoning service never lets Gemma free-associate over a transaction history. Every case is first converted into an **evidence pack** — a numbered list of atomic, source-traceable facts (`EV-001: ACC-1001 → ACC-2044, ₹9,90,000, 2026-06-02, flagged structuring`, `EV-019: 12 accounts share FAILED KYC + shell company "Orion Holdings Pvt Ltd"`, etc.) — and the prompt instructs the model through six explicit steps in order: (1) restate material evidence with its `ev_id`, (2) determine the behaviour pattern, (3) judge evidence sufficiency, (4) write a 30-second investigation summary, (5) list follow-up questions, (6) draft the STR narration sentence-by-sentence, citing `ev_id`s inline and listing every rupee amount cited. The system prompt is explicit that "if the evidence does not show it, do not write it" and that amounts must be copied verbatim, never computed or rounded.
- **Schema-constrained decoding**, not GBNF-by-hand. The original plan specified a hand-written `.gbnf` grammar file consumed directly by `llama.cpp`. In practice we used **Ollama's `response_format: json_schema`**, which compiles the same JSON schema into an equivalent llama.cpp decoding grammar under the hood — giving the identical structural guarantee (an out-of-dictionary `gos_tag` is a token sequence the sampler physically cannot produce, masked before sampling rather than filtered after generation) through a schema definition instead of a hand-authored grammar file. Property order in the schema (`evidence_assessment → behaviour_pattern → evidence_sufficiency → investigation_summary → suggested_questions → gos_tag → narration → amounts_cited → recommended_action`) structurally enforces the same evidence-before-conclusion ordering the original GBNF plan called for.
- **Belt-and-braces deterministic grounding** on top of the grammar. The grammar guarantees *structure* (a valid enum tag, correctly-shaped JSON); it does not by itself guarantee that a cited rupee figure is real. So every STR sentence is additionally run through a regex-based grounding verifier that checks every cited amount and every `EV-xxx` reference against the actual case data (transactions, per-sender/receiver/pair aggregates, and figures quoted in engine rule alerts). Any sentence with an unverifiable claim is hard-capped into the "red — verify" confidence band regardless of how fluent or confident the model's own logprobs made it look.
- **Local RAG for PMLA/RBI/FIU-IND regulation citations.** A curated corpus of ~10 real regulation sections (PMLA §3 and §12(1)(b), PML Rules 2005, RBI KYC Master Direction, FIU-IND STR Guidance red-flag indicators) is embedded with **`nomic-embed-text` served locally through Ollama**, cached to disk, and searched by cosine similarity — replacing the originally planned `chromadb` + `sentence-transformers` stack with an equivalent, lighter-weight local pipeline. If the embedding model is ever unavailable, the search degrades gracefully to keyword-overlap scoring rather than blocking the pipeline.
- **A learned risk-scoring layer instead of hand-tuned rules** (the engine side's Gemma usage). Each case is serialized into a natural-language description (transaction pattern, KYC red flags, shared-PAN groups, XGBoost scores, currencies involved) and passed through Gemma with `output_hidden_states=True`; the middle transformer layer's hidden state is mean-pooled into a single vector per case; `PCA(64)` reduces dimensionality to avoid overfitting on a small case count; a `LogisticRegressionCV` classifier (inner 5-fold CV over 10 candidate regularization strengths, balanced class weights) turns that into a risk probability. This is **reading the model's internal representation of the case, not asking it to self-report a score** — the reason it needs local weights and cannot be done against a cloud API.

### What frameworks did we use?

**Backend (engine, port 8001):** FastAPI, SQLAlchemy (SQLite, Postgres-swappable via `DATABASE_URL`), pandas, `networkx≥3.0` (native `louvain_communities`), `transformers` + `torch` (Gemma activation extraction), `scikit-learn` (`PCA`, `LogisticRegressionCV`, `StandardScaler`), `xgboost`, `faker`, Pydantic v2.

**Backend (reasoning, port 8002):** FastAPI, **Ollama** (both chat-completion and embedding endpoints, via its OpenAI-compatible REST API — no `llama-cpp-python` binding needed), `requests`, Pydantic v2. Deliberately dependency-light: no `torch`, `chromadb`, or `sentence-transformers` on this side — Ollama already hosts the model, and local embeddings come from the same Ollama instance.

**Frontend:** React 18 + Vite 5 + Tailwind CSS v4 + Recharts (transaction-amount and comparison charts) + a hand-rolled, dependency-free SVG force-directed graph layout (~40 lines of physics — chosen over `react-force-graph` specifically so the relationship graph has nothing external to break on stage).

---

## 📖 Problem Statement

Small NBFCs and co-operative banks in India must comply with PMLA/RBI anti-money-laundering obligations under steep per-day penalties, but face two compounding constraints that larger banks don't:

1. **Data cannot leave the premises.** RBI data-localization requirements and India's DPDP Act make cloud-hosted AML tools a non-starter for this segment — not a preference, a legal boundary.
2. **Rule-based detection is noisy by construction.** Threshold- and velocity-based rules (the only tool most small institutions can afford) produce a 90%+ false-positive rate, and every one of those false positives still consumes a compliance officer's time to manually pull the transaction history, check for related accounts, find the applicable regulation section, and write up a conclusion — a process that can take hours per alert.

The compliance burden this creates is disproportionate: a small institution processing a fraction of a large bank's transaction volume can still face the same absolute filing deadlines and the same absolute penalties for missing them, with none of the large bank's staffing or tooling budget.

---

## 💡 Solution

**SentinelAI** is a two-plane, fully on-premise AML co-investigator:

1. **Batch plane (engine, :8001) — turns a raw transaction feed into a short list of investigable cases.** A cheap rule-engine first pass flags obviously suspicious accounts (velocity, near-threshold structuring, repeated near-threshold transfers between the same pair); an XGBoost model trained on 5M+ labeled transactions refines that flag into a per-transaction anomaly score; a transaction-only graph is built from the surviving transactions and clustered with Louvain community detection, collapsing what started as thousands of individual alerts into a handful of coherent cases; a Gemma activation probe reads the case's own internal representation to produce a calibrated risk score, benchmarked live against the XGBoost and naive-rule-count baselines it's meant to beat.

2. **Interactive plane (reasoning + frontend, :8002 / :5173) — turns a case into a defensible, filing-ready STR.** For any case, an evidence pack is assembled deterministically (timeline, entity relationships including shared-PAN rings and repeat-beneficiary patterns, KYC/shell-company flags, rule alerts, regulation citations) and validated by a **hard evidence gate**: if a case lacks a minimum bar of evidence (≥3 transactions, ≥1 relationship, ≥1 regulation citation, every item source-traceable), the system refuses to draft an STR at all and returns `INSUFFICIENT_EVIDENCE` — a genuine safety property, not a demo trick. Cases that pass the gate go through a single schema-constrained Gemma pass that produces an investigation summary, follow-up questions, and a structured STR draft whose ground-of-suspicion tag is drawn from a closed, legally-meaningful dictionary the model cannot deviate from. Every sentence in the draft is then colour-banded by a fused confidence score (the model's own token-level logprobs, discounted by an independent grounding check against the actual ledger), so the human reviewer sees exactly which claims to verify before they attest and file.

The system's core design principle: **the model drafts, evidence gates, humans attest.** Nothing is ever filed without a human decision, and nothing reaches the human without first passing a real evidentiary bar.

---

## 🧠 Gemma Integration

Gemma is used in three architecturally distinct ways, each exploiting something only local model weights make possible:

1. **Activation probing for risk scoring** (engine). A trained linear probe reads Gemma's internal hidden-state representation of a case — not a prompted self-report — through `output_hidden_states=True`, mean-pooled at the middle transformer layer. This is the calibrated, tunable decision boundary that stands in for a rigid rule threshold, and it is architecturally impossible against a cloud API, which only ever exposes generated text, never internal activations.
2. **Schema-constrained decoding for the STR draft** (reasoning). The ground-of-suspicion tag, the evidence-then-conclusion ordering, and the overall JSON shape of every investigation output are enforced at the decoding level — invalid tokens are masked before sampling, not filtered from a free-form response afterward. A malformed tag is not possible to produce, not merely unlikely.
3. **Native token log-probabilities for a confidence heat-map** (reasoning). Every STR sentence is scored by the mean of its own generation-time logprobs, exponentiated into a 0–1 confidence and fused with an independent deterministic grounding check. This is the model quantifying its own uncertainty at the token level — again only available when the weights are local, since a cloud completion endpoint returns text, not per-token probabilities.

None of these three — activation probing, logit-masked constrained decoding, or per-token confidence — is available against a hosted API that only returns finished text. For this project, local Gemma is not a convenience; it is the only architecture that is simultaneously legally compliant (no data leaves the building) and technically instrumentable in the ways the system's trust story depends on.

---

## 🧰 Technology Stack

### Engine (batch/static plane — Person 1, port 8001)

- **API:** FastAPI, Pydantic v2, `uvicorn`
- **Data:** pandas, the real Kaggle "IBM Transactions for Anti Money Laundering (AML)" dataset (`HI-Small_Trans.csv`, ~5.08M rows for the pretrained baseline; a ring-preserving stratified sample for local runs)
- **Graph & clustering:** `networkx≥3.0` (native `louvain_communities`, no separate `python-louvain` dependency), a single undirected weighted transaction-only graph
- **ML:** `transformers` + `torch` (Gemma-3-1B activation extraction, bfloat16), `scikit-learn` (`StandardScaler`, `PCA`, `LogisticRegressionCV`, `StratifiedKFold`), `xgboost` (17-feature transaction-level classifier, native JSON export/import)
- **Synthetic identity generation:** `faker`, deterministic PAN-format and Indian-name generation, seeded (`RNG_SEED=42`)
- **Persistence:** SQLAlchemy ORM over SQLite (Postgres-swappable via `DATABASE_URL`) — six tables: `cases`, `transactions`, `graph_edges`, `entities`, `comparison_metrics`, `audit_log`

### Reasoning (interactive/dynamic plane — Person 2, port 8002)

- **API:** FastAPI, Pydantic v2, `uvicorn`
- **Model serving:** **Ollama** (local, air-gapped), `gemma4:latest` (4B) for reasoning with `gemma4:12b` as a config-flag upgrade, `nomic-embed-text` for regulation search — both accessed through Ollama's OpenAI-compatible REST endpoint (schema-constrained chat completions with logprobs, plus an embeddings endpoint), no `llama-cpp-python` or `chromadb` dependency
- **Evidence & reasoning pipeline:** pure-Python evidence builder, relationship miner (including a DFS-based circular-flow/round-tripping detector), regex-based deterministic grounding verifier, a hash-chained append-only audit log (each entry embeds the SHA-256 of the previous entry — any retroactive edit is detectable)
- **Export:** stdlib `xml.etree.ElementTree` for a well-formed FIU-IND STR XML skeleton, round-trip-verified before it ever leaves the service

### Frontend

- React 18, Vite 5, Tailwind CSS v4, Recharts
- A dependency-free hand-rolled SVG force-directed graph renderer for the entity-relationship view
- A CVD-validated (colourblind-safe) categorical and status colour palette, applied consistently across risk bands, confidence bands, and entity types

### Cross-cutting

- A single frozen `shared_contracts.py` (Pydantic models) is the entire interface contract between the two services — both import it verbatim, so the two planes were built in parallel by two people without blocking each other, and merged in an afternoon once both sides honored the schema.

---

## ⭐ Key Features

- **Alert-to-case collapse via graph community detection.** Hundreds of individual rule/ML alerts on a real 100k-transaction sample collapsed into **1,217 coherent, investigable cases** via Louvain clustering on a transaction-only graph (identity edges are deliberately excluded from clustering so communities reflect real money movement, not signals the pipeline invented itself).
- **Three-model risk comparison, evaluated honestly on held-out data**, not asserted: the probe, an XGBoost baseline, and a naive rule-count baseline are all scored on the same held-out stratified test split (AUPRC, AUROC, precision, recall) and the comparison is exposed live via `/metrics/comparison` and rendered as a chart — including the possibility that the learned model doesn't win, reported honestly either way.
- **A hard evidence gate that actually blocks filing.** `INSUFFICIENT_EVIDENCE` is not a UI message — it is enforced in the pipeline before any call to the language model happens for that path, and separately re-checked by a schema field the model itself must set (`evidence_sufficiency`), giving two independent stop conditions rather than one.
- **A confidence heat-map that is not just the model's self-belief.** Confidence fuses the model's own token logprobs with an independent, deterministic check of every cited figure against the actual ledger — a fluent, high-logprob sentence citing a number that isn't in the transaction data is still forced into the red band.
- **A live, on-stage-safe grammar-rejection demo.** A standalone widget lets an analyst paste a malformed STR fragment (e.g. an invalid ground-of-suspicion tag) and see it structurally rejected, with an explanation of why the same rejection is *impossible to trigger* during real generation — the invalid tokens are never reachable in the first place.
- **Ring-based synthetic identity that mirrors real laundering structure**, not random noise: shared PANs, shared shell-company names, and FAILED/PENDING KYC statuses are generated *only* for account rings actually connected via the dataset's real laundering label — connected components on the true positive subgraph — so the "beneficial owner controls multiple accounts" pattern the system is meant to catch is genuinely present in the data it's evaluated against, not hand-scripted.
- **A drift watchdog on the frozen XGBoost model.** Every seed run computes a Population Stability Index between the live transaction-amount distribution and the distribution the pretrained model was trained on; if it exceeds a standard-rule-of-thumb threshold (PSI > 0.25), the pipeline automatically warm-starts additional boosting trees on the current data rather than silently serving a stale model or requiring a manual retrain.
- **Currency-general evidence and grounding.** The real dataset spans multiple currencies (`US Dollar`, `Euro`, `Rupee`, and others) rather than INR-only; amount formatting and the grounding verifier's regex extraction both handle symbol-prefixed, comma-grouped, and bare numeric formats across all of them, discovered and fixed during live integration against real engine cases.
- **Hash-chained audit log and FIU-IND XML export.** Every evidence-assembly, investigation, and attestation event is appended to a tamper-evident log; attesting an STR exports a well-formed XML file, verified by a round-trip parse before it's returned.

---

## 🧩 Challenges

**What was the hardest part of building this in one day?**

- **Getting Gemma to run at all, twice, for two different jobs, on real hardware.** The original plan called for `gemma-3-4b-it` for the activation probe; it needed 16GB+ RAM and segfaulted under what was actually available, so the probe was moved to `gemma-3-1b-it` instead — a real hardware constraint discovered mid-build, not a design preference. Separately, on the reasoning side, `gemma4:12b` split roughly 35%/65% between CPU and GPU once its full context window was loaded, pushing a single investigation past 10 minutes — undemoable. Switching the default to `gemma4:latest` (4B) brought a full investigation down to roughly 60–80 seconds with no measurable drop in output quality on the hero cases, with 12B kept as an opt-in upgrade path for a machine with more VRAM.
- **Ollama's default context window silently truncated the exact output we needed.** Because the 4B/12B Gemma builds emit an internal "reasoning channel" of tokens before their final answer, Ollama's default 4096-token context was consumed by that reasoning before the constrained JSON answer even began — generation would finish with `finish_reason: length` and an *empty* answer, which surfaced as a confusing runtime error rather than an obvious one. The fix was auto-provisioning a derived Ollama model with an explicitly widened context window (`num_ctx`) at service startup, sized to comfortably cover real evidence prompts (which run to roughly 4,000+ tokens on genuinely large cases) plus the reasoning channel plus the answer — while staying small enough to keep the KV cache fully on GPU for the 4B model rather than triggering CPU offload.
- **A hallucinated-looking number that was actually a formatting bug, not a model failure.** Early in integration, transactions cited in the evidence pack were truncated to whole rupees (`.0f` formatting) while the underlying ledger stored exact decimal amounts — so the model faithfully copied the number it was shown, and the grounding verifier then correctly flagged it as unverifiable against the *undisplayed* exact figure, producing 80 false "amount violations" on a single real case. The fix was showing the model the exact figure in the evidence line in the first place, plus accepting integer-rounded citations of a decimal ledger amount as a legitimate display convention rather than a fabrication — after the fix, the same case produced zero violations.
- **Two people's contracts had to converge exactly, twice.** The two planes were built in parallel against a single frozen `shared_contracts.py`, but the engine's richer real-world output (per-transaction XGBoost scores, KYC status, shared-PAN groups, rule-alert detail strings) required extending that contract with new optional fields partway through the build. Every new field had to default safely so day-one mock fixtures kept validating unchanged, and every field name (`from_account` vs. `sender_account`, `entities[].owner_pan` vs. a transaction-level PAN field, `risk.p` nested vs. a flat `risk_p`) had to be reconciled explicitly rather than discovered at merge time — solved by writing an interface contract document before the merge, not after, with a literal copy-paste-ready schema diff and a full example JSON payload.
- **A full merge against real, non-synthetic data surfaced bugs synthetic fixtures never would have.** The real dataset uses full-name currencies (`"US Dollar"`, `"Euro"`) rather than ISO codes or INR-only, which broke amount formatting and the grounding regex the moment real engine cases were wired in — both had to be generalized to handle symbol-prefixed, comma-grouped, and bare numeric formats across currencies, a class of bug that never appeared against the hand-built development fixtures.
- **A stale Vite dependency cache produced a blank frontend with no obvious cause.** After several rounds of restarting the dev server across config and dependency changes, the served JSX transform fell out of sync with the actual plugin configuration, producing a `ReferenceError` on first render with no code-level explanation — resolved by clearing Vite's dependency-optimization cache and confirming a clean re-transform, and documented as the first thing to try if the frontend ever behaves inconsistently with the source again.
- **The one-day time box forced real trade-offs, not shortcuts taken quietly.** Document/KYC-image evidence is explicitly stubbed with synthetic fixtures rather than a real vision pipeline; the regulation corpus is a curated ~10-section subset rather than the full PMLA/RBI/FIU-IND text; company-ownership edges (`OWNED_BY`/`DIRECTOR_OF`) are defined in the contract but never actually produced by the current identity-generation pipeline, which only emits shared-PAN-based ring evidence. Each of these is a deliberate, disclosed simplification rather than a silent gap — the honest position given the time available.

---

## 🚀 Future Scope

- **Fine-tune a small, dedicated typology/sufficiency classifier via QLoRA**, evaluated separately from the STR-drafting model, so a learned decision (which ground-of-suspicion tag applies, whether evidence is sufficient) is fed into the constrained drafter as a fixed input rather than left to the drafter to decide inline — improving tag accuracy without touching the stock model whose token logprobs the confidence heat-map depends on. (A larger fine-tune of the STR narrator itself was deliberately not pursued: it would need hundreds of gold-standard STR examples that don't exist, and any weight shift risks silently distorting the token logprobs the whole confidence-and-trust story is built on.)
- **Vision extraction over real scanned KYC/invoice documents.** Document evidence is currently a stubbed, synthetic fixture, clearly labeled as such; wiring Gemma's vision tower to a real OCR/field-extraction pass over scanned identity documents and invoices is the natural next capability.
- **Expand the regulation corpus from a curated subset to full PMLA/RBI/FIU-IND text**, with the existing embedding-based retrieval scaling to a much larger corpus without architectural change.
- **Company-ownership graph layer.** Extend synthetic identity generation to produce genuine `OWNED_BY`/`DIRECTOR_OF` relationships (multi-entity corporate structures, not just shared-PAN rings), which the contract already supports but the current pipeline does not populate.
- **Retrain the activation probe on an institution's own historical STR/CTR outcomes** rather than a single public dataset's labeled typologies, closing the gap between a generically-trained probe and a production deployment calibrated to one institution's actual filing history.
- **Postgres in production, SQLite for the demo** — the schema is already portable via a single `DATABASE_URL` environment variable; moving to Postgres is an infrastructure change, not a data-model one.
- **A production-grade FIU-IND XML schema.** The current export is a faithful, well-formed skeleton built without access to the non-public production XSD; formalizing it against the real FIU-IND electronic filing specification is a natural hardening step before any real filing use.

---

## 🎬 The Prototype

- **Demo video:** *[Insert link to your 2-minute demo video here]*
- **GitHub repository:** *[Insert link to your GitHub repo here]*
- **Kaggle write-up / notebook:** *[Insert link to your Kaggle notebook, if applicable, here]*

**Suggested demo script** (~3–4 minutes): paste/point at a transaction batch → dashboard collapses the batch into a handful of risk-banded cases → open a RED case → timeline, relationship graph, and evidence assemble automatically → run the live Gemma investigation → the constrained STR draft appears with each sentence colour-banded by confidence → open the grammar-rejection widget and show a malformed tag being refused, and explain that the same rejection is structurally impossible to trigger mid-generation, not merely unlikely → attest → FIU-IND XML downloads → show the audit log's intact hash chain. For contrast, open a thin, low-evidence case and show the system refusing to draft an STR at all.

---

## Honest Numbers (measured, not asserted)

Reported exactly as measured, including where they might raise a follow-up question — because being asked "how do you know?" and having a real answer is the point:

- **XGBoost baseline (Kaggle-trained on the full dataset):** AUROC = 0.934, AUPRC = 0.046, on a held-out test set of 1,015,669 transactions with 1,035 positives (~0.1% positive rate). The large gap between a strong AUROC and a low AUPRC is expected and explainable under this level of class imbalance — AUPRC is a much harder bar than AUROC when positives are this rare, and both numbers are reported rather than only the flattering one.
- **Local 100k-row sample seed run** (used for the live demo, not the Kaggle-scale run above): 1,108 rule alerts across 1,080 flagged accounts → 4,834 XGBoost-confirmed suspicious transactions → **1,217 Louvain communities → 1,217 cases**. On this run's held-out probe test split (244 cases, 100 positive): the case-level risk model reached AUPRC 0.903 / AUROC 0.905 / precision 0.892 / recall 0.740, against XGBoost's case-aggregated AUPRC 0.857 and the naive rule-count baseline's AUPRC 0.429 — the ordering the whole "learned model beats a rule engine" pitch depends on held on this run.
- **Important honesty note on the number above:** this particular 100k-row local run's risk model was trained and evaluated using the **TF-IDF fallback vectorizer**, not real Gemma hidden-state activations — `USE_GEMMA=0` was used for that seed run for speed and reliability during integration. The architecture (mean-pool → PCA(64) → `LogisticRegressionCV`) is identical either way, and the same code path runs on genuine Gemma activations when `USE_GEMMA=1` (verified working separately, with its own hardware trade-offs described in the Challenges section above) — but the specific 0.903/0.905 numbers above came from the text-vectorizer fallback, not the activation probe, and should be captioned that way anywhere they're quoted rather than implied to be Gemma's numbers.
- **Live investigation latency** (reasoning service, `gemma4:latest` 4B, real engine-produced cases): 60–80 seconds per case for a full constrained investigation + STR draft, with zero grounding (amount/citation) violations after the currency and truncation fixes described above.
