# SPEC CARD 3 — Integration & Merge (anyone can run this)

**Mission:** Take `engine` (Person 1, port 8001) and `reasoning` (Person 2, port 8002), wire them into one live system, replace every mock with the real thing, and rehearse the demo until it's boring.

Do not start this until both Spec Card 1 and Spec Card 2 have hit their "Definition of Done" independently. Merging two half-finished services wastes more time than it saves.

---

## 1. Repo layout (target state)

```
sentinelai/
  shared_contracts.py       # frozen since day 0, both services import it unchanged
  engine/                   # Person 1's code, untouched
  reasoning/                # Person 2's code, untouched
  frontend/                 # React app, now pointed at real APIs
  docker-compose.yml         # optional: run engine + reasoning + postgres together
  .env                        # ENGINE_API_URL, REASONING_API_URL, GEMMA_MODEL_PATH
  README.md
```

## 2. Merge checklist

- [ ] **Contract diff check first.** Diff `engine/shared_contracts.py` and `reasoning/shared_contracts.py` against the frozen root copy. If either drifted, fix it *before* wiring anything — this is almost always where "integration day" pain actually comes from.
- [ ] Bring up `engine` alone. Hit `GET /cases` and `GET /cases/{hero_case_id}` manually (curl or `/docs` Swagger UI). Confirm the JSON validates against `Case` in `shared_contracts.py`:
  ```python
  from shared_contracts import Case
  import requests, json
  data = requests.get("http://localhost:8001/cases/CASE-042").json()
  Case.model_validate(data)  # raises if the contract was violated
  ```
- [ ] Bring up `reasoning` alone, still pointed at its **mock** fixtures. Confirm `/investigate/{id}` still works.
- [ ] **Swap the wire, not the code.** In `reasoning`, change the one line/config that fetches a Case — from `fixtures/mock_cases.json` to `GET http://localhost:8001/cases/{id}`. Nothing else in `reasoning` should need to change if both sides honored the contract.
- [ ] Run one real hero case end-to-end through both services via curl/Postman before touching the frontend:
  `engine /cases/{id}` → `reasoning /evidence/{id}` → `reasoning /investigate/{id}` → `reasoning /export/{id}`.
- [ ] Point the frontend's `engineClient.ts` and `reasoningClient.ts` at the real ports. Remove any mock-JSON fallback flag.
- [ ] Wire the threshold slider on the Dashboard to `engine`'s `/risk/threshold` and confirm the band counts actually move.
- [ ] Wire the PR-AUC comparison chart to `engine`'s `/metrics/comparison`.
- [ ] Full click-through: Dashboard → click a hero case → Timeline/Graph/Evidence/Investigation/STR+Heatmap all populate → Attest → Export downloads a valid XML.

## 3. Demo reliability pass

- [ ] Pick **one primary hero case** for the live demo and **two backups** in case something glitches on stage. All three must be pre-verified end-to-end the night before.
- [ ] Decide what's genuinely live vs. what's pre-warmed:
  - The Louvain clustering / probe scoring can be **pre-computed** and just displayed — don't re-run training live, that's not the interesting part anyway.
  - The **GBNF live-rejection** demo and **one real `/investigate` call on stage** should be genuinely live — that's the proof it's not smoke and mirrors.
- [ ] Time the full demo script (see Section 5) with a stopwatch. If it's over ~4 minutes, cut a tab, don't cut the grammar-rejection moment or the confidence heat-map — those are your two highest-signal beats for the 30% Gemma Integration score.
- [ ] Record a terminal/video backup of the full flow in case live wifi/hardware fails during judging — the handbook explicitly accepts this as a submission format.

## 4. `docker-compose.yml` (optional, use if you have 20 minutes to spare)

```yaml
services:
  engine:
    build: ./engine
    ports: ["8001:8001"]
    environment:
      - DATABASE_URL=sqlite:///./engine.db
  reasoning:
    build: ./reasoning
    ports: ["8002:8002"]
    environment:
      - ENGINE_API_URL=http://engine:8001
      - GEMMA_MODEL_PATH=/models/gemma-3-4b-it.gguf
    volumes:
      - ./reasoning/models:/models
  frontend:
    build: ./frontend
    ports: ["5173:5173"]
    environment:
      - VITE_ENGINE_URL=http://localhost:8001
      - VITE_REASONING_URL=http://localhost:8002
```

Not required — running three `uvicorn`/`vite` processes locally in separate terminals is equally fine for a hackathon and has less to break.

## 5. Demo script (reuse, don't reinvent)

> Paste a SAML-D batch → dashboard collapses hundreds of alerts to 5 cases → open Case #42 → timeline + graph + evidence self-assemble → Gemma suggests next questions and cites the PMLA section → grammar-valid STR drafts → sentences light green/red by the model's own confidence → analyst clicks attest → FIU-IND XML exports.

Narrate the *why* at two points: when the grammar rejects a malformed tag ("this isn't a filter, the model structurally cannot produce an invalid field here"), and when the heat-map lights a sentence red ("the model is telling the analyst which claim to double-check before signing off").

## 6. Final pre-submission checklist

- [ ] GitHub repo is public, has this README at the root, and both `engine/` and `reasoning/` have their own short setup notes.
- [ ] Kaggle write-up references the four form answers verbatim (Track Selection, AI & Gemma Usage, Project Idea) — see `04_README_main.md`.
- [ ] Working demo recorded as a fallback, even if you're doing it live.
- [ ] Every team member's Gemma usage is clearly attributed in the write-up (activation probe = Person 1, grammar-constrained generation + confidence = Person 2) — judges score "Gemma Integration" partly on how well you can *explain* what you did, not just that it works.
