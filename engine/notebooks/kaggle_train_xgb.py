"""
viGEMMAlya — XGBoost Training Script for Kaggle
================================================
Paste this entire file into a Kaggle notebook (Code cell).
Run it on the "IBM Transactions for Anti Money Laundering (AML)" dataset.

Dataset path on Kaggle:  /kaggle/input/ibm-transactions-for-anti-money-laundering-aml/

Recommended file: HI-Small_Trans.csv  (~5.5M rows, ~0.5% illicit ratio)
Runtime: ~5-8 min on Kaggle CPU (4 cores, 16 GB RAM)

Outputs (download from /kaggle/working/):
  xgb_pretrained.json       — XGBoost native model (no pickle issues)
  xgb_pretrained_meta.json  — p75, p95, eval metrics

Then drop both files into your local:
  engine/data/xgb_pretrained.json
  engine/data/xgb_pretrained_meta.json

The engine auto-loads them on next seed run (takes priority over local pkl).
"""

# ── Cell 1: Install ────────────────────────────────────────────────────────────
# xgboost is already on Kaggle. scikit-learn too.
# Just verify:
import subprocess
subprocess.run(["pip", "install", "--quiet", "xgboost>=2.0.0"], check=False)

# ── Cell 2: Imports ────────────────────────────────────────────────────────────
import os
import json
import numpy as np
import pandas as pd
from xgboost import XGBClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    average_precision_score, roc_auc_score, classification_report,
    precision_recall_curve,
)

# ── Cell 3: Config ─────────────────────────────────────────────────────────────
# Change this if you want to use a different file.
# HI = High Illicit ratio (better signal). Small fits in RAM easily.
CSV_FILE = "/kaggle/input/ibm-transactions-for-anti-money-laundering-aml/HI-Small_Trans.csv"

# Set to None to use all rows. 500_000 is a good fast test.
SAMPLE_N   = None
TEST_SIZE  = 0.2
RANDOM_SEED = 42
OUT_DIR    = "/kaggle/working"

# ── Cell 4: Column mapping (mirrors engine/ingestion/load_saml_d.py) ──────────
def load_ibm_aml(csv_path: str, sample_n=None) -> pd.DataFrame:
    df = pd.read_csv(csv_path, low_memory=False)
    print(f"Raw shape: {df.shape}")
    print(f"Columns:   {list(df.columns)}")

    # IBM AML has two columns both named "Account".
    # pandas auto-suffixes the second as "Account.1" when reading.
    rename = {}
    seen_account = False
    for col in df.columns:
        key = col.strip().lower().replace("_", " ")
        if key == "account":
            if not seen_account:
                rename[col] = "sender_account"
                seen_account = True
            else:
                rename[col] = "receiver_account"
        elif key == "account.1":
            # pandas auto-suffixes the duplicate "Account" column as "Account.1"
            rename[col] = "receiver_account"
        else:
            mapping = {
                "from bank":           "sender_bank",
                "to bank":             "receiver_bank",
                "amount paid":         "amount",
                "payment currency":    "payment_currency",
                "amount received":     "amount_received",
                "receiving currency":  "received_currency",
                "payment format":      "payment_type",
                "is laundering":       "is_laundering",
                "timestamp":           "timestamp",
            }
            rename[col] = mapping.get(key, col.strip().lower().replace(" ", "_"))

    df = df.rename(columns=rename)

    # Timestamp
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    else:
        df["timestamp"] = pd.Timestamp("2024-01-01")

    # Numeric coercions
    df["is_laundering"] = pd.to_numeric(df["is_laundering"], errors="coerce").fillna(0).astype(int)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)

    # If "Amount Paid" was 0, use "Amount Received" as fallback
    if "amount_received" in df.columns:
        mask = df["amount"] == 0
        df.loc[mask, "amount"] = pd.to_numeric(
            df.loc[mask, "amount_received"], errors="coerce"
        ).fillna(0.0)

    # Defaults for optional columns
    for col, val in [
        ("payment_currency",  "USD"),
        ("received_currency", "USD"),
        ("sender_bank",       "Unknown"),
        ("receiver_bank",     "Unknown"),
        ("payment_type",      "SWIFT"),
    ]:
        if col not in df.columns:
            df[col] = val

    df = df.dropna(subset=["sender_account", "receiver_account"])
    df["sender_account"] = df["sender_account"].astype(str).str.strip()
    df["receiver_account"] = df["receiver_account"].astype(str).str.strip()

    # Stratified sample (preserves laundering ratio)
    if sample_n is not None and len(df) > sample_n:
        pos = df[df["is_laundering"] == 1]
        neg = df[df["is_laundering"] == 0]
        pos_ratio = len(pos) / len(df)
        n_pos = max(2, int(sample_n * pos_ratio))
        n_neg = sample_n - n_pos
        df = pd.concat([
            pos.sample(min(n_pos, len(pos)), random_state=RANDOM_SEED),
            neg.sample(min(n_neg, len(neg)), random_state=RANDOM_SEED),
        ]).sample(frac=1, random_state=RANDOM_SEED).reset_index(drop=True)

    launder = df["is_laundering"].sum()
    pct = 100 * launder / max(len(df), 1)
    print(f"Loaded {len(df):,} rows — {launder:,} laundering ({pct:.3f}%)")
    return df


# ── Cell 5: Feature extraction (MUST match engine/risk/baselines.py exactly) ──
# IBM AML uses full names ("Wire", "US Dollar"); synthetic uses ISO codes ("SWIFT", "USD").
# Both map to the same integers so the model is portable between datasets.
_PAYMENT_TYPE_MAP = {
    "Reinvestment": 0, "Wire": 1, "Cheque": 2, "Credit Card": 3,
    "Cash": 4, "ACH": 5, "Bitcoin": 6,
    "SWIFT": 1, "NEFT": 7, "RTGS": 8, "IMPS": 9,
    "Debit card": 3, "Credit card": 3, "Cash Deposit": 4,
}
_CURRENCY_MAP = {
    # Natural case (as in IBM AML CSV)
    "US Dollar": 0, "Euro": 1, "UK Pound": 2, "Yuan": 3,
    "Bitcoin": 4, "Yen": 5, "Canadian Dollar": 6, "Rupee": 7,
    "Mexican Peso": 8, "Australian Dollar": 9, "Ruble": 10,
    # Uppercase (what .str.upper() produces)
    "US DOLLAR": 0, "EURO": 1, "UK POUND": 2, "YUAN": 3,
    "BITCOIN": 4, "YEN": 5, "CANADIAN DOLLAR": 6, "RUPEE": 7,
    "MEXICAN PESO": 8, "AUSTRALIAN DOLLAR": 9, "RUBLE": 10,
    # ISO codes
    "USD": 0, "EUR": 1, "GBP": 2, "CNY": 3, "JPY": 5,
    "CAD": 6, "INR": 7, "MXN": 8, "AUD": 9, "AED": 11, "SGD": 12,
}

FEATURE_NAMES = [
    "log_amount", "hour", "is_night", "is_unsocial_hour",
    "currency_mismatch", "pay_currency_id", "rcv_currency_id",
    "payment_type_id", "cross_institution", "is_swift", "is_cash",
    "near_5l", "near_10l", "near_25l",
    "above_p75", "above_p95", "log_amount_sq",
]


def build_feature_matrix(df: pd.DataFrame):
    p75 = float(df["amount"].quantile(0.75))
    p95 = float(df["amount"].quantile(0.95))
    print(f"Amount p75={p75:,.0f}  p95={p95:,.0f}")

    amounts     = df["amount"].fillna(0).values.astype(float)
    timestamps  = df["timestamp"]
    pay_currs   = df["payment_currency"].fillna("USD").str.upper().str.strip()
    rcv_currs   = df["received_currency"].fillna("USD").str.upper().str.strip()
    pay_types   = df["payment_type"].fillna("SWIFT").str.strip()
    src_banks   = df["sender_bank"].fillna("").astype(str)
    dst_banks   = df["receiver_bank"].fillna("").astype(str)

    hours = pd.to_datetime(timestamps, errors="coerce").dt.hour.fillna(12).values.astype(int)

    log_amt    = np.log1p(amounts)
    is_night   = (hours < 6).astype(np.float32)
    is_unsoc   = ((hours >= 22) | (hours < 6)).astype(np.float32)
    c_mismatch = (pay_currs.values != rcv_currs.values).astype(np.float32)
    pay_cid    = pay_currs.map(_CURRENCY_MAP).fillna(6).values.astype(np.float32)
    rcv_cid    = rcv_currs.map(_CURRENCY_MAP).fillna(6).values.astype(np.float32)
    pt_id      = pay_types.map(_PAYMENT_TYPE_MAP).fillna(8).values.astype(np.float32)
    cross_inst = ((src_banks.values != dst_banks.values) &
                  (src_banks.values != "") & (dst_banks.values != "")).astype(np.float32)
    is_swift   = pay_types.isin(["SWIFT", "Wire"]).values.astype(np.float32)
    is_cash    = pay_types.isin(["Cash", "Cash Deposit"]).values.astype(np.float32)

    # These thresholds are in USD equiv; IBM AML dataset amounts are in USD
    near_5l    = ((amounts >= 47_000)  & (amounts < 50_000)).astype(np.float32)
    near_10l   = ((amounts >= 95_000)  & (amounts < 100_000)).astype(np.float32)
    near_25l   = ((amounts >= 240_000) & (amounts < 250_000)).astype(np.float32)
    above_p75  = (amounts > p75).astype(np.float32)
    above_p95  = (amounts > p95).astype(np.float32)
    log_sq     = log_amt ** 2

    X = np.column_stack([
        log_amt, hours.astype(np.float32), is_night, is_unsoc,
        c_mismatch, pay_cid, rcv_cid, pt_id, cross_inst,
        is_swift, is_cash,
        near_5l, near_10l, near_25l,
        above_p75, above_p95, log_sq,
    ]).astype(np.float32)

    y = df["is_laundering"].values.astype(int)
    return X, y, p75, p95


# ── Cell 6: Load data ──────────────────────────────────────────────────────────
df = load_ibm_aml(CSV_FILE, sample_n=SAMPLE_N)


# ── Cell 7: Build features ─────────────────────────────────────────────────────
X, y, p75, p95 = build_feature_matrix(df)
print(f"\nFeature matrix: {X.shape}  Labels: {y.sum():,} positive / {(~y.astype(bool)).sum():,} negative")


# ── Cell 8: Stratified split ───────────────────────────────────────────────────
X_train, X_test, y_train, y_test = train_test_split(
    X, y, test_size=TEST_SIZE, stratify=y, random_state=RANDOM_SEED
)

# Inner validation set for early stopping
X_tr, X_val, y_tr, y_val = train_test_split(
    X_train, y_train, test_size=0.15, stratify=y_train, random_state=RANDOM_SEED
)

print(f"Train: {len(y_tr):,}   Val: {len(y_val):,}   Test: {len(y_test):,}")
neg_tr, pos_tr = int((y_tr == 0).sum()), int((y_tr == 1).sum())
scale_pos_weight = neg_tr / max(pos_tr, 1)
print(f"scale_pos_weight = {scale_pos_weight:.2f}  (neg={neg_tr:,} pos={pos_tr:,})")


# ── Cell 9: Train XGBoost ──────────────────────────────────────────────────────
model = XGBClassifier(
    n_estimators=500,
    max_depth=6,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    min_child_weight=5,
    gamma=1,
    scale_pos_weight=scale_pos_weight,
    eval_metric="aucpr",
    early_stopping_rounds=30,
    random_state=RANDOM_SEED,
    n_jobs=-1,
    device="cpu",           # Kaggle free CPU; set to "cuda" if using GPU accelerator
    tree_method="hist",     # fastest on CPU for large datasets
)

model.fit(
    X_tr, y_tr,
    eval_set=[(X_val, y_val)],
    verbose=50,
)

print(f"\nBest iteration: {model.best_iteration}")
imp = model.feature_importances_
top5 = np.argsort(imp)[::-1][:5]
print(f"Top features: {[FEATURE_NAMES[i] for i in top5]}")


# ── Cell 10: Evaluate on held-out test set ────────────────────────────────────
probs = model.predict_proba(X_test)[:, 1]
preds = (probs >= 0.5).astype(int)

auprc = average_precision_score(y_test, probs)
auroc = roc_auc_score(y_test, probs)
report = classification_report(y_test, preds, output_dict=True, zero_division=0)

eval_report = {
    "level":       "transaction",
    "dataset":     os.path.basename(CSV_FILE),
    "test_n":      int(len(y_test)),
    "test_pos":    int(y_test.sum()),
    "auprc":       round(float(auprc), 4),
    "auroc":       round(float(auroc), 4),
    "precision_1": round(report.get("1", {}).get("precision", 0), 4),
    "recall_1":    round(report.get("1", {}).get("recall", 0), 4),
    "f1_1":        round(report.get("1", {}).get("f1-score", 0), 4),
    "model":       "xgboost",
    "best_iteration": int(model.best_iteration),
}

print(f"\n=== Test-set metrics ===")
print(f"  AUPRC : {auprc:.4f}")
print(f"  AUROC : {auroc:.4f}")
print(f"  P@0.5 : {eval_report['precision_1']:.4f}")
print(f"  R@0.5 : {eval_report['recall_1']:.4f}")
print(f"  F1@0.5: {eval_report['f1_1']:.4f}")


# ── Cell 11: Save outputs ──────────────────────────────────────────────────────
json_out = os.path.join(OUT_DIR, "xgb_pretrained.json")
meta_out = os.path.join(OUT_DIR, "xgb_pretrained_meta.json")

model.save_model(json_out)  # XGBoost native format — no pickle issues on load

meta = {
    "p75":         p75,
    "p95":         p95,
    "eval_report": eval_report,
    "feature_names": FEATURE_NAMES,
}
with open(meta_out, "w") as f:
    json.dump(meta, f, indent=2)

print(f"\nSaved: {json_out}")
print(f"Saved: {meta_out}")
print("\nDownload both files from Kaggle output tab.")
print("Drop them into:  engine/data/xgb_pretrained.json")
print("                 engine/data/xgb_pretrained_meta.json")
print("Then run:        python -m engine.db.seed --force")
