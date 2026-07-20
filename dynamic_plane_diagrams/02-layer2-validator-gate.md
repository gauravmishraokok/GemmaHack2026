# Layer 2 — Evidence Validator + Hard Gate

Every fact that goes into the pack must be traceable to a real source. If a fact has no source it's flagged as missing, and if that missing fact is critical, plain code refuses to let Layer 3 even start — a hard stop written as an if-statement, not a prompt instruction.

```mermaid
flowchart LR
    E1["Claim slot: shared director"] --> Q1{"Backed by a<br/>real source?"}
    Q1 -- "Yes, Neo4j query result" --> OK1["Kept - tagged with source_ref"]
    Q1 -- "No, nothing backs it" --> BAD1["Logged in missing_evidence[]"]

    BAD1 --> G{"Any CRITICAL<br/>evidence missing?"}
    G -- Yes --> HALT["str_draft never runs<br/>(a code check, not a prompt instruction)"]
    G -- No --> PASS["Proceed to Layer 3"]
```
