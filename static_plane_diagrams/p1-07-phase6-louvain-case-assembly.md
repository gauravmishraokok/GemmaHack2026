# Person 1 — Phase 6: Louvain Clustering + Case Assembly

Louvain finds the fraud rings (same idea as before), but case assembly now has three cleanup steps this version specifies precisely: shared-PAN detection, cross-community dedup, and size capping.

```mermaid
flowchart TB
    TG["Transaction-only graph"] --> Louvain["Louvain community detection"]
    Louvain --> Comm["Each community = one candidate case"]

    Comm --> Assemble["Assemble case:"]
    Assemble --> A1["Transactions: all confirmed txns\nbetween accounts in this community\n(each carries its xgb_score)"]
    Assemble --> A2["KYC data: pull synthetic entity\nrecords for every account\nin the community"]
    Assemble --> A3["shared_pan_groups: group accounts\nthat share the SAME PAN number\n= one owner, multiple accounts"]
    Assemble --> A4["Rule alerts: filter Phase 3's\nall_alerts down to this\ncommunity's accounts"]
    Assemble --> A5["Case label (probe training only):\nfraction of case's transaction amount\nthat is actually laundering, 0 to 1"]

    A1 --> Dedup{"Does this account also\nappear in another community?"}
    Dedup -- Yes --> Compare["Compare total XGBoost score\nacross transactions in each case"]
    Compare --> Keep["Account stays in the\nHIGHER-scoring case only"]

    A1 --> Cap{"Community bigger than\n50 txns / 30 entities?"}
    Cap -- Yes --> Trim["Keep only top-N by\nXGBoost score"]
    Cap -- No --> Full["Keep as-is"]

    Keep --> Case["Final assembled Case"]
    Trim --> Case
    Full --> Case
```

**Why `shared_pan_groups` is the headline field:** everything else in this pipeline is statistical suspicion. This one is close to direct proof — if three accounts that look unrelated on the surface all share one PAN number, that's one real person or entity secretly controlling all three. It's the single strongest, most citable fact in the whole case file, which is why it gets called out as first-class evidence rather than buried inside the entity records.

**Why dedup and size-capping matter for a demo:** without dedup, the same suspicious account could show up in two different "rings" on screen, which looks like a bug. Without a size cap, Louvain occasionally produces one giant blob community (a known quirk on dense real-world graphs) that would make one "case" contain hundreds of accounts — impossible for an analyst or for Gemma to reason about in one pass.
