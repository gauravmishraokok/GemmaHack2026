# ADDED — XGBoost Drift Detection (not in Person 1's original spec)

Person 1's XGBoost is a **static, frozen artifact** — trained once on 5M Kaggle rows, then just *loaded* on every normal run, never retrained unless Kaggle files are missing. That's fine for a hackathon demo, but it means the model has zero awareness of whether live transactions still look like what it trained on. This adds a watchdog around Phase 4 without touching how Phase 4 itself works.

```mermaid
flowchart TB
    subgraph Phase4["Phase 4 (unchanged)"]
        Cand["candidate_transactions\n(from Rule Engine)"] --> XGB["Pretrained XGBoost\n(17 features)"]
        XGB --> Scored["Every transaction gets xgb_score"]
        Scored --> Thresh["Threshold: 0.4\n(auto-lowers to 0.3 if\ntoo few survive)"]
        Thresh --> Confirmed["confirmed_transactions"]
    end

    subgraph Drift["ADDED: Drift Watchdog (runs alongside Phase 4)"]
        direction TB
        Baseline["Baseline: the Kaggle training\nfeature distribution + score\ndistribution (p75/p95 from\nxgb_pretrained_meta.json)"]
        Live["Live: this run's 17-feature\ndistribution + xgb_score distribution"]
        Baseline --> Test1["PSI or KS-test on features\n(are amounts/currencies/timing\nstatistically different now?)"]
        Live --> Test1
        Baseline --> Test2["Compare live p75/p95 of\nxgb_score to the saved\nKaggle baseline p75/p95"]
        Live --> Test2
        Test1 --> Flag{"Drift beyond threshold?"}
        Test2 --> Flag
    end

    Scored -.->|"feeds live distribution"| Live

    Flag -- "No drift" --> Quiet["Log to comparison_metrics,\nno action"]
    Flag -- "Drift detected" --> Warn["Warn: XGBoost may be stale\nfor this data.\nSuggested actions below."]

    Warn --> Act1["Recommend running with\n--force + fresh Kaggle-style\nsample to retrain"]
    Warn --> Act2["Flag threshold (0.4) as possibly\nmiscalibrated for current data\n- surfaced to whoever runs seed"]
```

**Why this reuses stuff Person 1 already built, instead of adding new infrastructure:** the Kaggle training metadata file (`xgb_pretrained_meta.json`) already stores `p75` and `p95` of the training score distribution — that was built for threshold selection, but it's exactly the baseline a drift check needs too. Same with `comparison_metrics` (Phase 8) — it's already the table built to answer "is this model still good?", so drift results log into the same place instead of inventing a new one.

**Why this doesn't touch the actual filtering logic:** the drift watchdog only *reads* the same feature vectors and scores that Phase 4 already computes — it runs alongside Phase 4, not inside its decision path. If it flags drift, nothing about this run's `confirmed_transactions` changes; it just raises a warning for a human (or a future automated retrain trigger) to act on. That keeps Person 1's existing, tested filtering behavior completely untouched.

**Two simple terms used above:**
- **PSI (Population Stability Index):** a standard number that measures "how much has this distribution of values shifted compared to a baseline" — small PSI means stable, large PSI means the data has moved.
- **KS-test (Kolmogorov-Smirnov test):** a statistical test that answers "are these two sets of numbers likely drawn from the same underlying distribution, or not" — used here to compare today's feature values against the Kaggle training values.
