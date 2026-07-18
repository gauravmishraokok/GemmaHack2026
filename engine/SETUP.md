# Engine Setup (Person 1)

## Quick start

```bash
# 1. Install dependencies
pip install -r engine/requirements.txt

# 2. Run from repo root — auto-seeds on first start
USE_GEMMA=0 uvicorn engine.api.main:app --port 8001 --reload
```

The server seeds itself on startup if the DB is empty. Set `USE_GEMMA=1` (default) to use real Gemma 3 4B hidden-state activations for the probe — requires ~8 GB VRAM. Set `USE_GEMMA=0` for the TF-IDF fallback (fast, no GPU needed).

## Manual seed

```bash
# Generate fresh data + train models + populate DB
USE_GEMMA=0 python -m engine.db.seed

# Force re-seed even if models exist
USE_GEMMA=0 python -m engine.db.seed --force
```

## API endpoints (port 8001)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/cases?risk_band=RED&limit=50` | List cases (filtered) |
| GET | `/cases/{case_id}` | Full case object |
| GET | `/cases/{case_id}/graph` | Entities + edges |
| POST | `/risk/threshold` `{"threshold": 0.7}` | Recompute risk bands |
| GET | `/metrics/comparison` | Gemma vs XGBoost vs rule-count PR metrics |

## Environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `sqlite:///engine/data/engine.db` | Database connection string |
| `USE_GEMMA` | `1` | Set to `0` to skip Gemma and use TF-IDF probe |

## Hero cases fixture

`engine/fixtures/hero_cases.json` — 5 pre-verified cases validating against `shared_contracts.py`.
Copy this to `reasoning/fixtures/mock_cases.json` so Person 2 can work without the live API.

## Gemma integration note

- `engine/risk/probe.py` extracts mid-layer hidden states from `google/gemma-3-4b-it` via HuggingFace `transformers`
- A `LogisticRegression` is trained on these pooled activations against SAML-D laundering labels
- Activations are cached to `engine/data/probe_cache/` — never re-run on every request
- This is separate from Person 2's `llama.cpp` usage (generation + GBNF) — two separate Gemma stacks for two separate jobs
