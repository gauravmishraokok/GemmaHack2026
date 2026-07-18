# SentinelAI — Reasoning & Investigation Service (Person 2, port 8002)

Takes a `Case`, assembles an evidence pack, reasons over it with **gemma4 via
Ollama under schema-constrained decoding**, scores every STR sentence with
the model's own token logprobs fused with deterministic grounding checks, and
exports an attested FIU-IND XML with a hash-chained audit trail. Fully
functional on mock cases — no dependency on Person 1.

## Run

```bash
# prerequisites: Ollama running locally with gemma4:latest and nomic-embed-text pulled
cd reasoning
pip install -r requirements.txt
python -m uvicorn api.main:app --port 8002
```

On first startup the service auto-creates `gemma4-sentinel` (a derived tag of
`gemma4:12b` with a 16k context window — shares weights, no extra disk).

No GPU / no Ollama? `SENTINEL_MOCK_LLM=1` runs everything with a deterministic
fake model so the API and frontend still work end to end.

## Environment

| Var | Default | Purpose |
|---|---|---|
| `OLLAMA_URL` | `http://localhost:11434` | Ollama endpoint |
| `OLLAMA_BASE_MODEL` | `gemma4:latest` | base model to derive from (4B ≈ 60s/investigation; `gemma4:12b` works but needs the VRAM to avoid CPU offload) |
| `OLLAMA_MODEL` | `gemma4-sentinel` | model used for generation (auto-provisioned) |
| `NUM_CTX` / `MAX_TOKENS` | `8192` / `5000` | context + generation budget |
| `EMBED_MODEL` | `nomic-embed-text` | regulation semantic search |
| `ENGINE_API_URL` | *(unset)* | set to `http://localhost:8001` on integration day — cases then come from Person 1's engine instead of fixtures. That's the whole merge. |
| `SENTINEL_MOCK_LLM` | `0` | `1` = run without Ollama |

## API (contract responses validate against `shared_contracts.py` exactly)

| Method | Path | Returns |
|---|---|---|
| GET | `/health` | service + Ollama + audit-chain status |
| GET | `/cases`, `/cases/{id}` | `CaseSummary[]` / `Case` (fixtures or engine proxy) |
| POST | `/evidence/{id}` | `EvidencePack` (body `Case` optional) |
| POST | `/investigate/{id}` | `InvestigationResult` — the full constrained Gemma pass |
| GET | `/investigate/{id}/full` | cached result + evidence + diagnostics (frontend view) |
| GET | `/regulations/search?q=&k=` | `RegulationRef[]` |
| POST | `/export/{id}` (body `STRDraft`) | `{xml, audit_entry}` + writes audit log + file |
| POST | `/grammar/validate` | live-reject demo: `{valid, error, checks_failed}` |
| GET | `/schema/str` | the JSON schema compiled into the decoding grammar |
| GET | `/audit/{case_id}`, `/audit/verify` | audit trail / chain integrity |

## Demo beats

1. `POST /investigate/CASE-001` — structuring case: real single-pass constrained
   generation, gos_tag locked to the closed FIU dictionary, per-sentence
   confidence bands from real logprobs × grounding.
2. `POST /investigate/CASE-004` — thin case: the validator hard gate returns
   `INSUFFICIENT_EVIDENCE`, `str_draft` is null, provably no filing.
3. `/grammar/validate` with `"gos_tag": "LOOKS_KINDA_SUSPICIOUS"` — rejected;
   explain that during generation those tokens are masked before sampling.
4. Attest → `STR_CASE-001.xml` downloads, `GET /audit/verify` shows the intact
   hash chain.

Layout: `serving/` (Ollama client + constrained schema) · `evidence/` (timeline,
relationships incl. cycle detection, stubbed documents, regulation RAG,
validator gate) · `investigation/` (prompt, pipeline, grounding, confidence) ·
`export/` (FIU XML, hash-chained audit) · `api/` (FastAPI) · `fixtures/`.

See `../change.md` for every deviation from the original spec and why.
