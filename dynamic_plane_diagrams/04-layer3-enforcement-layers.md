# Layer 3 — Three Enforcement Layers for Evidence-First

Asking nicely in the prompt is not enough — the model can still jump to the conclusion early. Evidence-First is enforced three separate ways, each a backup for the one before it.

```mermaid
flowchart TB
    P["1. PROMPT<br/>6-step instructions telling it to list<br/>evidence before concluding<br/>(weakest - just a suggestion)"]
    Gm["2. GRAMMAR (GBNF)<br/>The JSON key order is physically<br/>enforced during generation<br/>(strongest - structural, not a suggestion)"]
    Cg["3. CODE GATE<br/>If evidence is empty, the code never<br/>even calls the model<br/>(a safety net before generation starts)"]
    P --> Gm --> Cg
```
