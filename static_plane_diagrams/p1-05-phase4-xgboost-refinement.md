# Person 1 — Phase 4: XGBoost (Transaction-Level Refinement)

Second pass. Scores each candidate transaction individually with the pretrained model and drops the ones XGBoost disagrees with.

```mermaid
flowchart TB
    CT["candidate_transactions\nfrom Phase 3"] --> Feat["Extract 17 features:\nlog(amount), log(amount)^2, hour of day,\nis-night, is-unsocial-hour, currency mismatch,\npayment currency ID, receiving currency ID,\npayment type ID, cross-institution flag,\nis-wire, is-cash, 3 near-threshold flags,\n2 percentile-vs-dataset flags"]
    Feat --> Model["Pretrained Kaggle XGBoost model\n(loaded, not retrained)"]
    Model --> Score["xgb_score appended\nto every transaction (0 to 1)"]

    Score --> Thresh{"xgb_score >= 0.4?"}
    Thresh -- Yes --> Keep["Kept: confirmed_transactions"]
    Thresh -- No --> Drop["Dropped -\nrule engine flagged it,\nbut XGBoost disagrees"]

    Keep --> Viable{"Enough confirmed txns\nsurvived? (e.g. >= 20)"}
    Viable -- "No" --> Lower["Auto-lower threshold\nto 0.3 and re-filter"]
    Viable -- "Still no" --> Warn["Warn + exit seed cleanly\n(don't write a broken/empty DB)"]
    Viable -- "Yes" --> Proceed["Proceed to Phase 5"]
    Lower --> Viable
```

**Why this step exists at all, given the Rule Engine already ran:** rules are deliberately dumb and wide (they're designed to catch *everything that might be suspicious*, tolerating false alarms). XGBoost is the model that actually learned, from 5 million real labeled transactions, what genuinely suspicious behavior looks like statistically — so it acts as a smarter second opinion that narrows the wide net the Rule Engine cast. A transaction has to pass *both* checks to be considered "confirmed."

**The 0.4 → 0.3 auto-lowering step is a practical safety valve:** Louvain clustering (next phase) needs a reasonable number of transactions to find meaningful communities in. If the threshold is too strict and almost nothing survives, there's nothing left to cluster — so the threshold automatically relaxes once, rather than the whole pipeline silently producing zero cases.
