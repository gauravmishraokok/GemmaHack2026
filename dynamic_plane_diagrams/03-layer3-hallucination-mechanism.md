# Layer 3 — Why Conclusion-First Causes Hallucination

Autoregressive means the model writes one word at a time, and each new word is chosen based on all words written so far. If the conclusion is written first, everything after it must stay consistent with a claim already on the page — the model can't take it back.

```mermaid
sequenceDiagram
    participant M as Gemma (autoregressive)
    Note over M: If it writes the conclusion FIRST...
    M->>M: writes "This is structuring."
    Note over M: Now every future word must sound<br/>consistent with a claim already on the page
    M->>M: invents supporting "evidence" to justify itself
    Note over M: It can't take it back - the sentence<br/>already exists in its own context
```

**The fix — Evidence-First flips the order:**

```mermaid
flowchart LR
    A["Evidence written FIRST<br/>(copied from EvidencePack)"] --> B["Conclusion generated SECOND<br/>(conditioned on real evidence<br/>already in context)"]
```
