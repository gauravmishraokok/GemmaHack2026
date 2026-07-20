# Person 1 — Phase 8: Model Evaluation

The phase that answers "is any of this actually working, or would a simpler approach do just as well?" — three scorers, ranked from dumbest to smartest, evaluated on the same held-out cases.

```mermaid
flowchart TB
    Held["20% held-out cases\n(with ground-truth labels\nfrom Phase 6)"] --> S1["Scorer 1: Rule count\n(dumbest baseline - just count\nhow many rule alerts a case has)"]
    Held --> S2["Scorer 2: Aggregated XGBoost\nmax*0.6 + mean*0.3 +\nhigh-risk-fraction*0.1"]
    Held --> S3["Scorer 3: Gemma probe\n(or TF-IDF fallback)"]

    S1 --> M["Compute for each:\nAUPRC, AUROC,\nprecision@0.5, recall@0.5"]
    S2 --> M
    S3 --> M

    M --> Store["comparison_metrics table"]
    Store --> Ep["/metrics/comparison\n/metrics/comparison/full"]
```

**Why compare all three instead of just trusting the fanciest one:** this is the honest version of "does the AI actually help?" If the Gemma probe doesn't clearly beat aggregated XGBoost, and XGBoost doesn't clearly beat simple rule-counting, that's important to know — and worth showing a judge, since it proves the numbers aren't cherry-picked. **Note the aggregation formula for Scorer 2** — it turns a *list* of per-transaction xgb_scores (Phase 4 output) into one *case-level* number using a weighted blend of the highest score, the average score, and the fraction of transactions that were "high risk" — that's what makes it comparable apples-to-apples against the probe's single per-case `risk_p`.
