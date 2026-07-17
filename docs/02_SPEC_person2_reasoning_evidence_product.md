# SPEC CARD 2 — Person 2: Reasoning, Evidence & Product (Interactive Plane + Frontend)

**Codename:** `reasoning`
**Port:** `8002`
**One-line mission:** Take a Case, assemble an evidence-backed EvidencePack, run it through Gemma under grammar-constrained decoding to produce an investigation summary and a filing-locked STR, score every sentence's confidence from real logprobs, and present the whole thing in a dashboard a compliance analyst would actually trust.

You build against a **mock Case** on day one. You never wait on Person 1.

---

## 1. You own

| Component | Layer (from architecture) |
|---|---|
| Gemma serving via `llama.cpp` (grammar + logprobs) | serving |
| Timeline / relationship / document / regulation services | ⑥ evidence construction |
| Evidence validator + hard gate | ⑥ |
| Evidence-first prompt + GBNF grammar | ③ Gemma reasoning |
| Confidence heat-map | ⑦ trust layer |
| Human review + audit log write | ⑧ |
| FIU XML export | ⑨ |
| React frontend (entire dashboard) | product |

## 2. You do NOT own

Rule engine, graph construction, clustering, activation probe, Postgres schema for cases. That's Person 1 (Spec Card 1).

## 3. Assumption you make about Person 1 (so you're never blocked)

**ASSUME the `Case` object below until Person 1's real `/cases/{id}` is live.** They will hand you `fixtures/hero_cases.json` on day one — matching `shared_contracts.py`'s `Case` model exactly. Build your entire pipeline against those 3–5 fixture cases. When Person 1's API is up, you change one config value (`ENGINE_API_URL`) and nothing else should break, because you never touched the schema.

Also assume: **risk band thresholds are `RED ≥ 0.7`, `YELLOW ≥ 0.4`, else `GREEN`** until Person 1's threshold endpoint is live.

---

## 4. Tech stack

`llama-cpp-python` (or the `llama.cpp` server binary with `--grammar-file`), a Gemma 3 4B **GGUF** build (search Hugging Face for `gemma-3-4b-it-GGUF`, or convert yourself with `llama.cpp/convert_hf_to_gguf.py` if no pre-converted GGUF is available), `chromadb` + `sentence-transformers` (regulation RAG), `fastapi`, `uvicorn`, `pydantic`. Frontend: `React` + `Vite`, `Tailwind`, `recharts` (PR-AUC chart, band counts), a lightweight graph renderer (`react-force-graph-2d` or hand-rolled SVG if you want zero extra deps).

## 5. Folder structure

```
reasoning/
  serving/
    gemma_server.py         # llama.cpp wrapper, grammar-constrained generate()
    grammar/
      str_output.gbnf
  evidence/
    timeline.py
    relationships.py         # pure Python over Case.graph_edges — no DB needed
    documents.py              # STUBBED: 2-3 synthetic invoice/KYC fixtures
    regulations.py             # chromadb RAG over PMLA/RBI/FIU-IND text
    validator.py                # hard gate
  reasoning/
    prompt.py                    # evidence-first, 6-step prompt template
    confidence.py                  # logprobs -> sentence bands
  export/
    fiu_xml.py
    audit_log.py
  api/
    main.py                        # FastAPI app
  fixtures/
    mock_cases.json                 # copy of Person 1's hero_cases.json until real API is live
    sample_docs/                     # 2-3 fake invoice/KYC images or JSON stand-ins
    regs/                              # 2-4 real PMLA/RBI/FIU-IND PDFs or extracted text
  shared_contracts.py                  # copied in verbatim, do not edit

frontend/
  src/
    api/
      engineClient.ts                   # calls port 8001 (or mock JSON while waiting)
      reasoningClient.ts                # calls port 8002
    components/
      Dashboard.tsx                       # band counts + threshold slider
      CaseView/
        Timeline.tsx
        GraphView.tsx
        Evidence.tsx
        Investigation.tsx
        STRHeatmap.tsx
      GrammarDemo.tsx                       # live "paste invalid tag -> rejected" widget
```

---

## 6. Build order

### Phase A — Gemma serving (do this first, it unblocks everything else)
- [ ] Get Gemma 3 4B running under `llama.cpp` with grammar support. Verify a plain generate call works before touching grammar.
- [ ] Write a minimal `.gbnf` that just constrains output to a JSON object with one enum field. Test that an out-of-vocabulary tag is **structurally impossible**, not filtered after the fact. This is your cheapest, highest-wow demo moment — get it working early and don't let it slip.
- [ ] Confirm `llama.cpp` returns per-token logprobs (`--logprobs` / equivalent API flag) — you need this for the confidence layer.

### Phase B — Evidence construction (build against mock cases)
- [ ] `timeline.py`: sort `Case.transactions` by `timestamp`, emit human-readable events.
- [ ] `relationships.py`: walk `Case.graph_edges` / `Case.entities`, surface `shared_director`, `linked_pan`, `repeat_beneficiary` patterns. This needs **nothing** from Person 1's live API — it's pure computation over the Case object you already have as a fixture.
- [ ] `documents.py`: **stub this.** Hand-craft 2–3 fake invoice/KYC records as JSON (`{"field": "GSTIN", "value": "...", "bbox": [...]}`) rather than wiring a real vision model unless you have hours to spare. Label it clearly as a stub in the write-up — judges respect an honest "simulated for demo speed" note far more than a broken live vision call.
- [ ] `regulations.py`: pull 2–4 real PMLA/RBI/FIU-IND public PDFs, chunk + embed with `sentence-transformers`, store in `chromadb`, expose a `search(query, k=3)` function.
- [ ] `validator.py`: for each required evidence slot (transaction pattern, at least one relationship, at least one regulation citation), check it's backed by a `source_ref`. If critical evidence is missing or `evidence == []`, return `status="INSUFFICIENT_EVIDENCE"` and **stop** — `str_draft` must never be generated in that case. This hard gate is a genuine safety/trust feature, keep it real, don't fake it for the demo.

### Phase C — Gemma reasoning under grammar
- [ ] `prompt.py`: implement the 6-step evidence-first prompt (list all evidence → summarize → determine pattern → check sufficiency → suggest next questions → draft STR).
- [ ] `str_output.gbnf`: full grammar enforcing `evidence_array → pattern → conclusion → gos_tag → narration`, with `gos_tag` as a closed enum from the FIU dictionary, and amounts constrained to values copied from the evidence pack (not freely generated — validate post-hoc that every cited amount exists in `Case.transactions`, as a belt-and-braces check on top of the grammar).
- [ ] `confidence.py`: per sentence, mean the token logprobs, `exp()` to get a probability-like score, bucket into green (>0.75) / yellow (0.5–0.75) / red (<0.5).

### Phase D — Export + audit
- [ ] `fiu_xml.py`: template-fill an FIU-IND STR XML skeleton from the `STRDraft` object.
- [ ] `audit_log.py`: append-only log of who/what/when/evidence-refs on every attest action.

### Phase E — Frontend
- [ ] `Dashboard.tsx`: red/yellow/green counts, threshold slider (calls Person 1's `/risk/threshold` or mock).
- [ ] `CaseView` tabs: Timeline, Graph, Evidence, Investigation (next questions + reg citations), STR+Heatmap (color each narration sentence by its band).
- [ ] `GrammarDemo.tsx`: standalone widget — analyst types/pastes a malformed `gos_tag`, shows the live rejection. Keep this simple and bulletproof; it's your best 30-second demo beat.
- [ ] Attest button → calls audit log → export XML → download.

---

## 7. API you must expose (port 8002)

| Method | Path | Returns |
|---|---|---|
| GET | `/health` | `{"status":"ok"}` |
| POST | `/evidence/{case_id}` (body: `Case`) | `EvidencePack` |
| POST | `/investigate/{case_id}` (body: `Case`) | `InvestigationResult` |
| GET | `/regulations/search?q=structuring` | `List[RegulationRef]` |
| POST | `/export/{case_id}` (body: `STRDraft`) | `{"xml": str}`, also writes audit log |
| POST | `/grammar/validate` (body: `{"raw": str}`) | `{"valid": bool, "error": str|null}` — powers the live-reject demo |

All response bodies must validate against `shared_contracts.py` models exactly.

## 8. Definition of done

- [ ] A malformed `gos_tag` is provably rejected at decode time, not by a post-hoc regex — be ready to explain the difference to a judge.
- [ ] At least one mock case correctly triggers `INSUFFICIENT_EVIDENCE` (build this test case deliberately — thin evidence, no relationships) to prove the hard gate is real.
- [ ] Every narration sentence in the STR view is colour-banded and the bands visibly vary (not all green — that looks faked).
- [ ] Full frontend flow works end-to-end against the **mock** cases before Person 1's API exists.
- [ ] Export produces a well-formed XML file that opens without error.

## 9. Common pitfalls

- Don't let the regulation RAG block Phase A/B — it's valuable but not the moat. If time runs short, hardcode 3–4 well-chosen PMLA/RBI section citations mapped by `gos_tag` instead of a live vector search, and say so honestly in the write-up.
- Logprobs from `llama.cpp` are usually natural-log — don't forget the `exp()` before turning them into a 0–1 confidence.
- Keep the mock `Case` fixtures byte-for-byte identical to what Person 1 promises to return — the merge (Card 3) will otherwise eat your whole afternoon on schema mismatches instead of five minutes.
