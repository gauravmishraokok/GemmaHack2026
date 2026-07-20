# Layer 3 — End-to-End Flow

```mermaid
flowchart TB
    EP["EvidencePack from Layer 2"] --> PR["Evidence-First Prompt<br/>(6 steps: list evidence, summarize,<br/>determine pattern, check sufficiency,<br/>suggest next questions, draft STR)"]
    PR --> GEN["llama.cpp generation<br/>UNDER the GBNF grammar<br/>plus logprobs turned on"]
    GEN --> OUT["Structured JSON output:<br/>evidence[], summary, pattern,<br/>gos_tag, narration, next_questions"]
    OUT --> LP["Per-token logprobs<br/>(how confident the model was<br/>on each word it chose)"]
    LP --> HM["Layer 4 heat-map:<br/>narration sentences colored<br/>green=confident amber=unsure red=shaky"]
```

**Logprob, in plain terms:** the log of the probability the model assigned to the word it picked. Close to 0 = very sure. Large negative number = it was guessing. Average per sentence, convert back with exp(), and you get a 0-1 confidence score per sentence.
