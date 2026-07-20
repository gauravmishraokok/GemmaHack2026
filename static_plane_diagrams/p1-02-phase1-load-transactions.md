# Person 1 — Phase 1: Load Raw Transactions

The entry point. Reads the raw IBM AML dataset and turns it into a clean DataFrame (a table in memory) the rest of the pipeline can trust.

```mermaid
flowchart TB
    CSV["HI-Small_Trans.csv\n(5 million rows, IBM AML dataset)"] --> Fix["Fix duplicate 'Account' column\n(pandas auto-renamed the second\none to 'Account.1' - unify it)"]
    Fix --> Types["Coerce types\n(dates parsed, amounts as numbers, etc.)"]
    Types --> Sample{"Sample size\nrequested?"}
    Sample -- "Yes, e.g. 500k rows" --> Strat["Stratified sampling by\n'is_laundering'\n(keeps the same ~0.1%\nlaundering ratio as the full data)"]
    Sample -- "No, use all rows" --> Full["Use full dataset"]
    Strat --> Clean["Clean transactions DataFrame"]
    Full --> Clean
```

**Why "stratified" sampling matters:** laundering transactions are only about 0.1% of the data — incredibly rare. If you just grabbed a random 10% of rows, you might end up with almost none of the rare laundering examples, which would make later training useless. Stratified sampling deliberately keeps the *same ratio* of laundering-to-clean transactions in the smaller sample as exists in the full dataset, so a 500k-row sample still has enough real laundering examples to learn from.

**One detail worth remembering:** the `is_laundering` column is ground truth — the actual real answer, only present because this is a research dataset. It gets used later (synthetic identity generation, probe training labels, evaluation) but it is **never sent to Person 2** — Person 2 only ever sees model *predictions*, never the answer key.
