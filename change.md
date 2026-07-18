# change.md — Person 2 (reasoning + frontend) deviations from the original plan

Everything here was a deliberate call made while building; the shared contract
(`shared_contracts.py`) was **not** touched — all `/evidence`, `/investigate`,
`/regulations/search` and `/export` response bodies still validate against the
frozen models, so Person 1's integration path is unchanged.

## 1. llama.cpp + GBNF → Ollama + JSON-schema-constrained decoding

**Original plan:** serve Gemma 3 4B GGUF via `llama.cpp` with a hand-written
`str_output.gbnf` grammar file.
**What was built:** the locally installed **gemma4:12b via Ollama**. Ollama's
`response_format: json_schema` is compiled internally into a llama.cpp decoding
grammar, so the guarantee is **identical** — invalid `gos_tag` tokens are masked
before sampling, structurally unreachable, not filtered post-hoc. Verified live:
a schema with a closed enum forces the tag into the dictionary, in the same call
that returns per-token logprobs.
**Why:** it's the model actually installed, one less serving stack to babysit,
and the pitch line ("the model physically cannot produce an invalid field")
survives intact. The demo talking point should say "schema-constrained decoding
(compiled to a llama.cpp grammar by Ollama)" instead of "GBNF file".
`serving/schemas.py` replaces `serving/grammar/str_output.gbnf`.

## 2. Confidence = logprobs × deterministic grounding (upgrade, not just logprobs)

The spec's confidence layer was `exp(mean token logprob)` per sentence. That's
implemented — Ollama's OpenAI-compatible endpoint returns real per-token
logprobs — but fused with a second, deterministic signal:

- every ₹ amount in a narration sentence is checked against the case's actual
  transactions (plus legitimate aggregates: per-sender / per-receiver / grand
  totals);
- every `EV-xxx` citation is checked against the evidence pack;
- `confidence = lm_conf × (0.4 + 0.6 × grounding)`, and any sentence with a
  failed check is **hard-capped into the red band** regardless of how fluent the
  model felt.

This means a hallucinated figure can never render green. Differentiator worth
30 seconds of demo time: "the heat-map is not just the model's self-belief — red
can mean *we checked, and that number isn't in the ledger*."

## 2b. Model size: gemma4:latest (4B) as the default, 12B as an option

The 12B build split 35% CPU / 65% GPU on the dev box once the KV cache was
included, putting a full investigation past 10 minutes — undemoable. The 4B
build (`gemma4:latest`) runs a complete constrained investigation in ~60s with
identical output quality on the hero cases (correct typology-specific GoS tag
for structuring vs round-tripping vs smurfing, evidence IDs cited inline, zero
grounding violations). Default is now `OLLAMA_BASE_MODEL=gemma4:latest`; set it
to `gemma4:12b` if the demo machine has VRAM to hold it fully.

Measured on the dev box, per full investigation: CASE-001 65s, CASE-002 62s,
CASE-003 57s (4B); >600s (12B, partial CPU offload).

## 3. gemma4 reasoning channel + context window

This gemma4 build emits reasoning-channel ("thinking") tokens before the final
answer. Two consequences handled in code:

- Ollama's default 4096-token context truncated generations before the
  constrained answer began. At startup the service auto-provisions a derived
  model **`gemma4-sentinel`** (`num_ctx=8192`, shares weights, zero extra disk)
  via `/api/create`. 8192 (not 16k) keeps the KV cache small enough to stay on
  GPU. Override with `OLLAMA_MODEL`/`NUM_CTX` env vars.
- Sentence confidence is aligned to the answer's exact token span inside the
  full (thinking + answer) logprob stream, so thinking tokens never pollute the
  heat-map.

## 4. chromadb + sentence-transformers → Ollama embeddings (nomic-embed-text)

Regulation search embeds the curated PMLA/RBI/FIU-IND corpus with the already
installed `nomic-embed-text` through Ollama's `/api/embed`, cosine-scored
in-process, vectors cached to disk. Same semantic-search capability, zero torch
/ chromadb install weight, still fully air-gapped, with a keyword-overlap
fallback if the embed model is missing. The corpus is 10 curated sections
(regulation text paraphrased for the demo — flag in the write-up, same as the
original "curated subset" plan).

## 5. Two-stage insufficiency gate (addition)

The deterministic validator gate from the spec is implemented as specified
(CASE-004 trips it; no STR object is ever created). Added on top: the
constrained schema forces the model to declare `evidence_sufficiency`
SUFFICIENT/INSUFFICIENT **before** it may emit a gos_tag — if the model itself
says INSUFFICIENT, the pipeline also stops. Two independent gates, one
deterministic, one model-judged.

## 6. Hash-chained audit log (upgrade)

`audit_log.py` is append-only JSONL where every entry embeds the SHA-256 of the
previous entry (genesis-anchored). Any retroactive edit breaks the chain;
`GET /audit/verify` checks it live. Cheap tamper-evidence, good compliance
story.

## 7. Structure / naming

- `reasoning/reasoning/` from the spec's tree is named `reasoning/investigation/`
  (a Python package importing `reasoning.reasoning` was asking for trouble).
- Frontend is JSX (not TS) for hackathon velocity; API client is one module
  (`src/api/client.js`) — the engine is reached **through** the reasoning
  service's `/cases` proxy, so integration is one backend env var
  (`ENGINE_API_URL=http://localhost:8001`) and the frontend never changes.
- Graph view is a hand-rolled SVG force layout (~40 lines of physics) instead of
  `react-force-graph` — zero dependencies, deterministic, cannot break on stage.
- `GET /cases` + `GET /cases/{id}` exist on :8002 (fixture-backed now,
  engine-proxying later). Extra endpoints beyond the spec: `/investigate/{id}/full`
  (cached rich view for the UI), `/schema/str`, `/audit/{case_id}`,
  `/audit/verify`.

## 8. Mock-LLM mode (addition)

`SENTINEL_MOCK_LLM=1` runs the entire service with a deterministic fake model —
schema-valid output, varied fake logprobs — so anyone can develop the frontend
or run CI without a GPU. `/health` reports it honestly.

## 10. Contract extension for Person 1's richer engine output

Person 1's final architecture produces four fields the day-0 `shared_contracts.py`
didn't have: per-transaction `xgb_score`, entity `kyc_status`/`entity_subtype`/
`jurisdiction`/`linked_company`, `Case.shared_pan_groups`, and `Case.alert_details`.
The full interface spec is `docs/05_INTERFACE_person1_to_person2.md` — that's the
document to hand Person 1.

Person 2's side is **already implemented** against it (not just specced):

- `shared_contracts.py` (reasoning copy) extended with all four, every new field
  **optional with a default** → day-0 fixtures and old engine output still validate
  (verified: CASE-001/004 load unchanged).
- `relationships.py` now synthesises `linked_pan` from `shared_pan_groups` even
  when the engine sends no LINKED_PAN edges (verified against an engine-shaped
  IBM-AML case: correct ring detected from `shared_pan_groups` + `owner_pan`).
- `builder.py` emits new evidence kinds `rule_alert` (from `alert_details`) and
  `kyc_flag` (FAILED KYC / shell entity / high-risk jurisdiction), and appends the
  XGBoost anomaly score to each transaction evidence line so the model can cite it.
- Frontend Evidence panel renders the two new kinds.

**Deliberately NOT changed:** the root `docs/00_shared_contracts.py` stays frozen
as the day-0 baseline. The extension lives as an explicit copy-paste diff in the
interface doc (§3, §10) so Person 1 applies the identical block; both copies are
then updated together at merge, exactly as SPEC card 3 prescribes.

## 11. Integration with Person 1's engine (merge of `origin/main`)

Merged `origin/main` ("Complete Batch Layer Push") into `dynamic-plane` and ran
the full integration guide. Results:

- **Contract**: root `shared_contracts.py` copied verbatim into `reasoning/`
  (differences vs. my copy were comments only — fields identical). All 5
  `engine/fixtures/hero_cases.json` cases `Case.model_validate()` clean; zero
  dangling graph edges; every txn account has an entity, as the guide promised.
- **Fixtures swapped**: `reasoning/fixtures/mock_cases.json` is now the engine's
  hero set (4 RED + 1 GREEN). The old hand-made SAML-D-style fixtures are gone;
  the GREEN case CASE-000391 (2 txns, no relationships) correctly trips the
  INSUFFICIENT_EVIDENCE hard gate, replacing my CASE-004 as the gate demo.
- **Currency handling generalised** (the one real incompatibility): engine emits
  IBM-AML full-name currencies ("Euro", "US Dollar", "Rupee"). Fixed
  `format_amount()` backend+frontend (₹ keeps Indian grouping; €/$/£ western;
  unknown names pass through), and widened the grounding amount extractor to
  symbol-prefixed, comma-grouped, and bare ≥5-digit figures — verified none of
  "score 0.94" / "48 hours" / "2026" false-match.
- **Grounding fixes found by integration testing**: (1) my evidence lines
  truncated decimal amounts (`.0f`), so the model faithfully cited a figure that
  then failed verification — evidence now shows the exact amount; (2)
  integer-rounded citations of decimal ledger amounts and figures quoted in
  engine `alert_details` are accepted as grounded; (3) parser crash on a lone
  "€," fixed. Result: CASE-000006 went from 80 false amount-violations to 0.
- **Verified live on real engine cases** (gemma4-sentinel, 16k ctx — raised from
  8k because real cases carry ~4.3k-token evidence prompts; fine on GPU for the
  4B): CASE-000006 → STRUCTURING (61-74s), CASE-000002 → LAYERING (71s), bands
  genuinely varied, XML export + audit chain intact.
- **Wire-swap proven**: reasoning ran with `ENGINE_API_URL=http://localhost:8001`
  against an engine-shaped server serving the hero fixtures — cases proxied,
  evidence built over the wire, live investigation OK. The real engine seed
  needs the IBM AML CSV (`engine/data/saml_d.csv`, gitignored, Kaggle download)
  which isn't on this machine — final live-engine run happens wherever that
  dataset lives; nothing on the reasoning side changes.
- KYC evidence is now **grouped** ("N accounts share FAILED KYC + shell company
  X: …") instead of one line per account — real cases have 30+ ring accounts and
  the aggregate is stronger evidence in fewer tokens.

## 12. Risk-band thresholds

Implemented as assumed in the spec (RED ≥ 0.7, YELLOW ≥ 0.4) with the dashboard
threshold slider recomputing bands via `GET /cases?threshold=` on the fixture
path. When Person 1's `/risk/threshold` endpoint is live, point the slider at it.
