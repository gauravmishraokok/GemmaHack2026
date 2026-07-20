# Person 1 — Overview (Seed Mode vs Serve Mode)

Two separate modes. Seed mode does the heavy one-time work of building the database. Serve mode is just a lightweight API sitting on top of what seed mode already built.

```mermaid
flowchart TB
    subgraph Seed["SEED MODE (run once / when data changes)"]
        direction TB
        P1["Phase 1: Load raw transactions"] --> P2["Phase 2: Synthetic KYC/PAN generation"]
        P2 --> P3["Phase 3: Rule Engine (coarse filter)"]
        P3 --> P4["Phase 4: XGBoost (transaction-level refinement)"]
        P4 --> P5["Phase 5: Graph construction"]
        P5 --> P6["Phase 6: Louvain clustering + case assembly"]
        P6 --> P7["Phase 7: Gemma probe (case-level risk scoring)"]
        P7 --> P8["Phase 8: Model evaluation"]
        P8 --> P9["Phase 9: Database persistence"]
        P9 --> P10["Phase 10: Fixtures output for Person 2"]
    end

    Seed --> DB[("SQLite / Postgres")]
    DB --> API["SERVE MODE\nFastAPI on port 8001\nread-only, fast"]
    API --> Person2["Person 2\n(Layer 2 + Layer 3)\nconsumes cases over HTTP"]
```

**Key idea to hold onto:** this whole pipeline runs *before* any analyst ever opens the app. By the time Person 2's code runs, all of Person 1's work (rules, XGBoost, clustering, Gemma probe scoring) is already sitting in the database as a finished "case." Person 2 never triggers any of Phases 1–10 directly — Person 2 just calls the API and reads what's already there.
