# SPEC CARD 1 — Person 1: Data & Intelligence Engine (Batch Plane)

**Codename:** `engine`
**Port:** `8001`
**One-line mission:** Turn raw SAML-D transactions into risk-scored, graph-clustered Cases using a real Gemma-activation probe, and serve them over a clean REST API that Person 2 and the frontend consume without ever needing to know how the sausage is made.

You are the source of truth for the contract. You never mock anything — you *are* what Person 2 mocks.

---

## 1. You own

| Component | Layer (from architecture) |
|---|---|
| Data ingestion + synthetic identity injection | pre-processing |
| Rule engine (velocity / threshold / structuring-proximity) | ① |
| Graph builder (networkx) | ② |
| Community detection (Louvain) | ③ |
| Gemma activation probe (risk scoring) | ④ primary |
| XGBoost + rule-count baselines | ④ comparison |
| Postgres/SQLite schema + case assembly | ⑤ |
| `engine` FastAPI service | contract surface |

## 2. You do NOT own

Evidence construction, Gemma text generation, GBNF grammar, confidence heat-map, frontend, FIU export. That's Person 2 (Spec Card 2). If you finish early, help them — don't creep into their files.

## 3. Assumption you make about Person 2 (so you're never blocked)

You need **nothing** from Person 2 to finish your work. You only need to **honor the schema** in `shared_contracts.py` exactly, since that's what they're building against. If you must deviate from a field name/type, post it in the team channel immediately — don't silently drift.

---

## 4. Tech stack

`pandas`, `networkx>=3.0` (has `louvain_communities` built in — no separate `python-louvain` needed), `transformers`, `torch`, `scikit-learn`, `xgboost`, `fastapi`, `uvicorn`, `pydantic`, `sqlalchemy` + `psycopg2-binary` (or swap to `sqlite3` if Postgres setup eats time — schema is portable, don't let infra block you), `faker` (synthetic KYC/PAN/GST).

## 5. Folder structure

```
engine/
  ingestion/
    load_saml_d.py         # reads the SAML-D CSV
    synth_identity.py      # injects PAN/director/company relationships
  rules/
    velocity.py
    threshold.py
    structuring.py
  graph/
    build_graph.py         # networkx graph from txns + synthetic identities
    cluster.py              # louvain_communities -> case groupings
  risk/
    probe.py                # Gemma hidden-state extraction + LogisticRegression
    baselines.py             # XGBoost + rule-count
    compare.py                # PR-AUC comparison data
  db/
    models.py                # SQLAlchemy models
    seed.py
  api/
    main.py                   # FastAPI app, imports shared_contracts.py
  fixtures/
    hero_cases.json            # see Section 8 — hand-verified demo cases
  shared_contracts.py           # copied in verbatim, do not edit
```

---

## 6. Build order

### Phase A — Data foundation
- [ ] Load SAML-D CSV. Typical columns are `Time, Date, Sender_account, Receiver_account, Amount, Payment_currency, Received_currency, Sender_bank_location, Receiver_bank_location, Payment_type, Is_laundering, Laundering_type` — **verify against your actual download**, column names/casing can vary by version.
- [ ] Write `synth_identity.py`: for every unique account ID, generate a synthetic PAN (`AAAAA9999A` format), owner name (Faker), and ~15% of accounts get attached to a synthetic Company + Director (Faker again). This is what makes "shared director" / "linked PAN" relationships possible — SAML-D alone is transaction-only and won't give you rich entity relationships for free.
- [ ] **Deliberately seed 3–5 "hero cases":** pick 3–5 Louvain communities (see Phase C) and inject *extra* shared attributes into them — same PAN across two accounts, same director across two companies, a repeat beneficiary pattern. This guarantees your live demo never lands on a boring, relationship-sparse cluster. Write these to `fixtures/hero_cases.json` early — Person 2 will build their entire pipeline against these before your API is even up.

### Phase B — Rule engine
- [ ] `velocity.py`: flag accounts with >N transactions in a rolling window (e.g. 5 txns / 48h).
- [ ] `threshold.py`: flag transactions clustering just under known reporting thresholds.
- [ ] `structuring.py`: flag repeated near-threshold transactions from/to the same account pair.
- [ ] Output: a flagged-alerts dataframe. This runs *before* the LLM — cheap first pass, per the "why not a rule engine" pitch (you're not replacing this, you're adding a learned layer on top of it).

### Phase C — Graph + clustering
- [ ] `build_graph.py`: `nx.MultiDiGraph` with edges `SENT` (txns), `OWNED_BY`, `DIRECTOR_OF`, `LINKED_PAN`.
- [ ] `cluster.py`: `nx.algorithms.community.louvain_communities(G, weight='weight')` on the flagged-account subgraph. Target: hundreds of alerts → a handful of cases (~5), matching the pitch's "500 alerts → 5 cases."

### Phase D — Risk scoring (the moat)
- [ ] `probe.py`:
  1. For each flagged alert/cluster, generate a short natural-language description (e.g. *"Account ACC0043 sent ₹4,95,000 to ACC0091 three times within 48 hours, both linked to PAN XYZ..."*).
  2. Run it through Gemma 3 4B via `transformers` (confirm exact HF repo id at build time — likely `google/gemma-3-4b-it`, check the model card) with `output_hidden_states=True`.
  3. Mean-pool the mid-layer hidden state (start with the middle layer index, tune from there).
  4. Train `sklearn.linear_model.LogisticRegression` on these pooled vectors against SAML-D's `Is_laundering` / typology labels.
  5. Output `p` (probability), `margin = abs(p - 0.5) * 2`, and `ood` = Mahalanobis distance of the activation from the training set centroid.
  6. This should take **minutes** to train once you have the pooled activations cached — don't retrain on every request, precompute and store.
- [ ] `baselines.py`: XGBoost on tabular features (amount, velocity count, time-of-day, etc.) and a naive rule-count score, trained on the same labels.
- [ ] `compare.py`: produce a precision/recall table across thresholds for all three models — this feeds the "we beat it" PR-AUC chart in the frontend.

### Phase E — Persistence + API
- [ ] `db/models.py`: `cases`, `case_members`, `transactions`, `audit_log` tables.
- [ ] `db/seed.py`: populate from Phases A–D output.
- [ ] `api/main.py`: FastAPI app — see Section 7 for the exact contract.

---

## 7. API you must expose (port 8001)

| Method | Path | Returns |
|---|---|---|
| GET | `/health` | `{"status":"ok"}` |
| GET | `/cases?risk_band=RED&limit=50` | `List[CaseSummary]` |
| GET | `/cases/{case_id}` | `Case` (full object, see `shared_contracts.py`) |
| GET | `/cases/{case_id}/graph` | `{"entities": List[Entity], "edges": List[GraphEdge]}` |
| POST | `/risk/threshold` `{"threshold": 0.6}` | `{"red": int, "yellow": int, "green": int}` — recomputes bands |
| GET | `/metrics/comparison` | `List[ComparisonMetric]` — for the PR-AUC chart |

All response bodies must validate against `shared_contracts.py` models exactly. Run `Case.model_validate(your_dict)` in a test before you consider an endpoint done.

## 8. Definition of done

- [ ] `GET /cases` returns at least 5 cases, at least 3 of which are your seeded "hero cases" with rich relationships.
- [ ] `GET /cases/{id}` for a hero case includes ≥2 relationship-bearing edges (`LINKED_PAN` or `DIRECTOR_OF`).
- [ ] `/risk/threshold` visibly changes the red/yellow/green counts.
- [ ] `/metrics/comparison` shows the Gemma probe beating both baselines on at least one threshold — if it doesn't, that's fine to show honestly, but check your labels/pooling layer first.
- [ ] `fixtures/hero_cases.json` was delivered to Person 2 **before** your API was live (this is what unblocks them from day one).

## 9. Common pitfalls

- Don't hook activations through `llama.cpp` — it doesn't expose hidden states. Use `transformers` for the probe, and let Person 2's `llama.cpp` handle generation + grammar. Two separate Gemma stacks for two separate jobs is correct, not wasteful.
- Louvain is stochastic — set a `seed` param and freeze it once you've picked your hero cases, or the demo cases will shuffle on you.
- If Postgres setup stalls for more than an hour, switch to SQLite immediately. Nobody is judging your database engine.
