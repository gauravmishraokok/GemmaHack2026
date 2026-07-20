# Layer 3 — GBNF Grammar-Constrained Decoding

Normally the model chooses from its entire vocabulary at every step. Grammar-constrained decoding hands it a much smaller menu of only the tokens that are legal right now, based on a grammar you wrote (GBNF).

```mermaid
flowchart TB
    S["Start of JSON output"] --> K1["Only legal next tokens:<br/>the key 'evidence':"]
    K1 --> AR["Must write a full array<br/>of evidence objects"]
    AR --> CLOSE{"Evidence array closed?"}
    CLOSE -- "No" --> AR
    CLOSE -- "Yes, only now" --> K2["Only legal next tokens:<br/>'summary', then 'pattern',<br/>then 'sufficient'"]
    K2 --> K3["Only legal next tokens:<br/>'gos_tag': one of a fixed<br/>list of 6 allowed tag strings"]
    K3 --> K4["'narration': free text<br/>(the ONLY unconstrained part)"]
```

**Two gotchas to remember:**
- The grammar file is never shown to the model — it only shapes what tokens are legal. The prompt still has to explain in words "list evidence first, then conclude."
- Grammar guarantees valid structure, not a finished answer — the model can run out of tokens mid-object. Use a generous max_tokens and wrap the parse in try/except.
