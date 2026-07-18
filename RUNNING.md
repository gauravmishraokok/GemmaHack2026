# Running SentinelAI locally

Three processes, three terminals, started in this order. Each step includes
the health check to run before moving to the next — don't skip them, a
downstream service starting against a dead upstream is the most common cause
of a confusing failure.

## Prerequisites (one-time)

```bash
# Ollama models (reasoning service)
ollama pull gemma4:latest
ollama pull nomic-embed-text

# Python deps
pip install -r engine/requirements.txt
pip install -r reasoning/requirements.txt

# Frontend deps
cd frontend && npm install && cd ..
```

The engine needs `engine/data/saml_d.csv` (the IBM AML `HI-Small_Trans.csv`
Kaggle dataset, renamed) and the two `xgb_pretrained*.json` files already in
`engine/data/` — those ship in the repo.

---

## Terminal 1 — Engine (port 8001)

First run seeds the database from the CSV (takes a few minutes on a 100k
sample). Subsequent runs just serve what's already seeded.

```bash
cd GemmaHack2026
USE_GEMMA=0 python -m engine.db.seed --sample 100000   # first time only
USE_GEMMA=0 python -m uvicorn engine.api.main:app --port 8001
```

`USE_GEMMA=0` uses the TF-IDF probe fallback (fast, no GPU). Drop it (or set
`USE_GEMMA=1`) to use real Gemma hidden-state activations — needs ~8GB VRAM
alongside whatever the reasoning service is using.

**Verify before continuing:**
```bash
curl http://localhost:8001/health          # {"status":"ok"}
curl "http://localhost:8001/cases?limit=1" # should return a case, not an error
```

---

## Terminal 2 — Reasoning (port 8002)

```bash
cd GemmaHack2026/reasoning
export ENGINE_API_URL=http://localhost:8001   # PowerShell: $env:ENGINE_API_URL = "..."
python -m uvicorn api.main:app --port 8002
```

Omit `ENGINE_API_URL` to run against the bundled mock fixtures instead of the
live engine (useful if Terminal 1 isn't up, e.g. developing the frontend
alone).

On first start the service auto-creates a derived Ollama model
(`gemma4-sentinel`) with a larger context window — this is a one-time
`ollama create` call, a few seconds.

**Verify before continuing:**
```bash
curl http://localhost:8002/health
# case_source should read "engine" (not "fixtures") if ENGINE_API_URL was set
# llm.ollama should read "up", model_available: true
```

If `llm.ollama` isn't `"up"`, Ollama itself isn't running — start it
(`ollama serve` or the desktop app) before this service, not after.

---

## Terminal 3 — Frontend (port 5173)

```bash
cd GemmaHack2026/frontend
npm run dev
```

Open **http://localhost:5173**.

**If the page loads blank with console errors:** this is almost always a
stale Vite dependency cache, not a real bug — Vite's pre-bundled deps
(`node_modules/.vite/`) can get out of sync with source after config or
dependency changes made while the dev server was running. Fix:

```bash
# stop the dev server first (Ctrl+C), then:
rm -rf node_modules/.vite dist
npm run dev
```

This forces Vite to re-optimize dependencies and re-transform every file from
scratch. It's always safe — nothing in `.vite`/`dist` is source, both are
regenerated. Do this any time the app behaves inconsistently with what you
just edited, before assuming the code is wrong.

---

## Stopping everything

Each terminal: `Ctrl+C`. Or, to force-kill by port (Windows PowerShell):

```powershell
Get-NetTCPConnection -LocalPort 5173,8001,8002 -State Listen -ErrorAction SilentlyContinue |
  ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
```

## Order matters

Engine → Reasoning → Frontend. Reasoning reads `ENGINE_API_URL` once at
startup (via `CaseStore.__init__`), so if you restart the engine, restart
reasoning after it if you want a fresh connection — though since it's stateless
HTTP per-request, an engine restart alone doesn't actually break a running
reasoning process, only a full engine *replacement* (e.g. re-seeding) might
leave case IDs reasoning doesn't recognize yet.
