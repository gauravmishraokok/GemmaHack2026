# Person 1 — API Layer (Serve Mode)

Once seeding is done, a FastAPI service exposes everything to Person 2 over HTTP. This is the actual contract boundary between the two of you.

```mermaid
flowchart TB
    Start["Service starts on port 8001"] --> Check{"Is the DB empty?"}
    Check -- Yes --> AutoSeed["Auto-run seed pipeline\n(Phases 1-10) first"]
    Check -- No --> Ready["Serve immediately"]
    AutoSeed --> Ready

    Ready --> E1["GET /health\nliveness check"]
    Ready --> E2["GET /cases\npaginated, filter by risk_band,\nsort by risk_p"]
    Ready --> E3["GET /cases/{case_id}\nfull case: txns, entities,\ngraph edges, shared_pan_groups"]
    Ready --> E4["GET /cases/{case_id}/graph\nsame data shaped for\ngraph rendering"]
    Ready --> E5["POST /risk/threshold\nrecompute risk bands with a new\nthreshold, no full re-run needed"]
    Ready --> E6["GET /metrics/comparison\n(+/full)\nmodel evaluation results"]

    E1 --> P2["Person 2's Layer 2\nreads these over HTTP"]
    E2 --> P2
    E3 --> P2
    E4 --> P2
    E5 --> P2
    E6 --> P2
```

**Two known gaps worth knowing about, since they'll bite before demo day if ignored:**
- **Pagination:** `/cases` currently hard-caps at 200. A full 5M-row run can produce thousands of cases — proper limit/offset pagination needs to go in before that becomes a problem.
- **CORS/auth:** currently wide open (`*`), which is fine for local dev on the same laptop, but should be locked down to just Person 2's service origin before any non-local demo setup (e.g. two laptops on venue wifi).

**What actually matters for you (Person 2) in the response payload:** `shared_pan_groups` (lead evidence — one owner, multiple accounts), `xgb_score` per transaction (a citable machine-learned anomaly number, e.g. "flagged with an XGBoost anomaly score of 0.91 against a 5M-transaction baseline"), `kyc_status`/`entity_type` per entity (directly citable risk indicators like FAILED KYC or Shell Company), and `alert_details` (formatted rule violations ready to drop into your evidence pack). Every one of these lets your Layer 2 evidence be grounded in a real structured field instead of something Gemma has to infer from raw numbers.
