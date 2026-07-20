# Person 1 — Phase 9 & 10: Persistence + Fixtures

Everything assembled gets written to a database, plus a small hand-picked sample gets exported as a standalone file so Person 2 can build against it without waiting for the full pipeline to run.

```mermaid
flowchart TB
    Case["Assembled, scored case"] --> DB["Phase 9: Database (SQLite,\nswappable to Postgres)"]

    subgraph Tables["Tables written"]
        T1["cases: risk_p, margin, ood,\nrisk_band, accounts,\nshared_pan_groups, member_alert_ids"]
        T2["transactions: from/to account,\namount, xgb_score, typology_flag"]
        T3["entities: entity_type, name,\npan_number, kyc_status,\nlinked_company, jurisdiction"]
        T4["graph_edges: SENT / OWNED_BY /\nDIRECTOR_OF / LINKED_PAN"]
        T5["comparison_metrics: from Phase 8"]
        T6["audit_log: ADDED — timestamp,\naction (SEED/RESCORE/\nTHRESHOLD_CHANGE), actor"]
    end

    DB --> Tables

    DB --> P10["Phase 10: Fixtures Output"]
    P10 --> Pick["Pick top 4 RED-band cases\n+ 1 GREEN-band case"]
    Pick --> Fixture["engine/fixtures/hero_cases.json\n(fully populated: KYC, shared PANs,\nxgb_scores, graph edges)"]
    Fixture --> Dev["Person 2 dev/offline use -\nbuild and test without\nwaiting on the full pipeline"]
```

**Why `audit_log` matters even though it's "just" a logging table:** it's what makes every case traceable later — who/what/when for every write. It's already defined in the schema; the only remaining work is actually populating it on every write, which is a small but important gap to close for compliance credibility, since a judge asking "how do you know nothing was tampered with after the fact" gets answered by this table, not by anything AI-related.

**Why a curated fixture file matters for a two-person team:** hero_cases.json means Person 2 (evidence construction + Gemma reasoning) never has to wait for a 5-million-row pipeline to finish just to test a UI tab or a prompt — 5 realistic, fully-populated cases spanning the whole risk spectrum (RED to GREEN) are enough to build and demo against in isolation.
