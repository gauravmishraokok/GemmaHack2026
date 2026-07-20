# Person 1 — Pre-Pipeline: Model Artifacts

Two trained models must exist before the pipeline can run properly. They're trained differently and at different times — this trips people up, so it's worth its own diagram.

```mermaid
flowchart TB
    subgraph XGB["XGBoost model"]
        direction TB
        X1["Trained ONCE, offline,\non Kaggle notebook"] --> X2["All 5,078,345 IBM AML\ntransactions used"]
        X2 --> X3["AUROC = 0.934\nat transaction level"]
        X3 --> X4["Exported as native XGBoost JSON\n(xgb_pretrained.json + meta.json)"]
        X4 --> X5["Loaded as-is by the pipeline\n- never retrained on a normal run"]
    end

    subgraph Probe["Gemma probe model"]
        direction TB
        G1["CANNOT be trained until\ncases exist"] --> G2["Needs Phases 1-6 to have\nrun at least once, producing\nlabeled cases"]
        G2 --> G3["First full pipeline run:\ntrain PCA(64) + LogisticRegression\non Gemma hidden states of cases"]
        G3 --> G4["Save as gemma_probe.pkl"]
        G4 --> G5["Every later run: LOAD the\nsaved probe, don't retrain"]
    end

    Note["--force flag on either model\ntriggers retraining"]
```

**Why the difference matters:** XGBoost scores individual *transactions*, so it can be trained straight from the raw Kaggle CSV, entirely separately from this pipeline. The Gemma probe scores whole *cases* (clusters of transactions + KYC + alerts) — and "cases" don't exist until Phases 1–6 have already run once and built some. That's a chicken-and-egg situation, solved by: run the pipeline once with an untrained probe, use that run's cases to train the probe, save it, and use the saved version forever after (until someone passes `--force`).

**Fallback, spelled out plainly:** if the Kaggle-trained XGBoost files are missing, the pipeline can locally train XGBoost on whatever small sample it has — but this is explicitly a lower-quality fallback (far less data), not the intended path.
