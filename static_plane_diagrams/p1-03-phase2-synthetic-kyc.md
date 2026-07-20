# Person 1 — Phase 2: Synthetic KYC/PAN Generation

The IBM AML dataset only has transactions — no identity documents, no PAN cards, no company names. This phase invents realistic identity data *on top of* the real transaction patterns, so laundering rings become visible through shared ownership, not just suspicious money movement.

```mermaid
flowchart TB
    IsLaundering["is_laundering column\n(ground truth, ring detection only)"] --> CC["Find connected components:\ngroups of accounts that transact\nwith each other AND have\nlaundering transactions"]
    CC --> Rings["Real laundering rings\n(from the actual dataset structure)"]

    Rings --> RingGen["For accounts IN a ring:"]
    RingGen --> R1["All accounts share ONE\nsynthetic PAN number\n(= one beneficial owner)"]
    RingGen --> R2["KYC status: FAILED or PENDING"]
    RingGen --> R3["Entity type: Shell Company"]
    RingGen --> R4["Linked to the same synthetic\nshell company name"]
    RingGen --> R5["Jurisdiction: High Risk"]

    Clean["For accounts NOT in a ring:"] --> C1["Unique PAN per account"]
    Clean --> C2["KYC status: VERIFIED"]
    Clean --> C3["Entity type: Individual or\nRegistered Business"]
    Clean --> C4["Jurisdiction: Standard"]

    R1 & R2 & R3 & R4 & R5 & C1 & C2 & C3 & C4 --> Append["Appended as new columns\non BOTH the sender side and\nreceiver side of every transaction"]
```

**The core idea in one sentence:** the dataset already tells you *which* accounts are truly part of a laundering ring (via `is_laundering` + the transaction graph) — this phase just gives those accounts a realistic paper trail of fake identity documents that *would* exist in real life if one person secretly controlled multiple accounts through a shell company.

**Why "shared PAN" is the single most important thing generated here:** in the real world, one person owning multiple bank accounts under different names is exactly how layering works. Giving every account in a real ring the *same* fake PAN number recreates that signal artificially — and it becomes the strongest, single clearest piece of evidence Person 2 can cite later ("these 3 accounts share one PAN — one entity controls all three").

**What Phase 3 onward can and can't see:** these new KYC columns get glued onto the transaction table, but the Rule Engine and XGBoost (next two phases) are deliberately kept blind to them — they only look at transaction behavior. The KYC columns just ride along silently until Phase 6, where they finally get used.
