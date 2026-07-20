# Person 1 — Phase 3: Rule Engine (Coarse Behavioral Filter)

First pass over the full dataset. Cheap, deterministic, transaction-behavior-only — the same three ideas as before, but now scoped precisely to what this build actually does.

```mermaid
flowchart TB
    Data["Consolidated dataset\n(transaction columns ONLY -\nKYC columns ignored entirely\nat this stage)"] --> V["Velocity detector\nmore than 5 txns in any\nrolling 48-hour window"]
    Data --> T["Threshold detector\namounts falling just below\nstatutory reporting limits"]
    Data --> S["Structuring detector\nrepeated near-threshold txns\nbetween the SAME sender-receiver pair"]

    V --> FA["flagged_accounts\n(set of account IDs)"]
    T --> FA
    S --> FA

    V --> AA["all_alerts\n(account, alert_type, detail)\nkept as evidence, sent to Person 2 -\ndoes NOT drive filtering"]
    T --> AA
    S --> AA

    FA --> Dedup["Deduplicate alerts per account\n(one account can trigger\nmultiple alert types)"]

    FA --> CT["candidate_transactions:\nALL transactions where sender\nOR receiver is in flagged_accounts\n(full row kept, KYC columns riding along unused)"]
```

**Important nuance versus a simpler design:** `all_alerts` is *not* a filter — it's evidence that gets carried all the way to the final case output for Person 2 to cite, but it has zero effect on which transactions survive to the next phase. The thing that actually decides what survives is `flagged_accounts`: any transaction touching a flagged account (as either sender or receiver) becomes a `candidate_transaction`. Filtering happens by *account*, but evidence is recorded by *alert*.
