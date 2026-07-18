"""
Load the IBM AML / SAML-D dataset into a pandas DataFrame.

Real dataset (Kaggle): "IBM Transactions for Anti Money Laundering (AML)"
https://www.kaggle.com/datasets/ealtman2019/ibm-transactions-for-anti-money-laundering-aml

Typical columns in the real download (casing varies by version):
  Timestamp | From Bank | Account | To Bank | Account | Amount Received |
  Receiving Currency | Amount Paid | Payment Currency | Payment Format | Is Laundering

Falls back to synthetic data only when the real CSV is absent.
"""

import os
import pandas as pd
from typing import Optional


# ---- Column normalisation maps -----------------------------------------------
# Keys are lowercase stripped versions of whatever the CSV header contains.
_COL_RENAME = {
    # Real IBM AML dataset variants
    "account":                  "sender_account",   # first Account col
    "account.1":                "receiver_account", # second Account col (pandas dupe suffix)
    "from bank":                "sender_bank",
    "to bank":                  "receiver_bank",
    "amount paid":              "amount",
    "payment currency":         "payment_currency",
    "amount received":          "amount_received",
    "receiving currency":       "received_currency",
    "payment format":           "payment_type",
    "is laundering":            "is_laundering",
    "timestamp":                "timestamp",
    # Synthetic / alternate naming
    "sender_account":           "sender_account",
    "receiver_account":         "receiver_account",
    "from":                     "sender_account",
    "to":                       "receiver_account",
    "from_bank":                "sender_bank",
    "to_bank":                  "receiver_bank",
    "sender_bank_location":     "sender_bank",
    "receiver_bank_location":   "receiver_bank",
    "laundering_type":          "laundering_type",
}


def load(csv_path: Optional[str] = None, sample_n: Optional[int] = None) -> pd.DataFrame:
    """
    Load and normalise the SAML-D CSV.

    Args:
        csv_path:  Path to CSV. Defaults to engine/data/saml_d.csv.
        sample_n:  If set, stratified-sample this many rows (preserves Is_laundering ratio).
                   Useful for dev iteration on the 11M-row real dataset.

    Returns:
        DataFrame with columns:
            sender_account, receiver_account, amount, payment_currency,
            received_currency, sender_bank, receiver_bank, payment_type,
            is_laundering, laundering_type, timestamp, txn_id
    """
    if csv_path is None:
        here = os.path.dirname(__file__)
        csv_path = os.path.join(here, "..", "data", "saml_d.csv")

    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            f"No dataset at {csv_path}. Download HI-Small_Trans.csv from the "
            f"'IBM Transactions for Anti Money Laundering (AML)' Kaggle dataset "
            f"and place it there."
        )

    df = pd.read_csv(csv_path, low_memory=False)

    # --- Normalise headers ---
    # The IBM dataset has two columns both named "Account"; pandas suffixes the second one.
    # We need to rename before lowercasing so .1 suffix is preserved.
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
        elif key in _COL_RENAME:
            rename[col] = _COL_RENAME[key]
        else:
            # snake_case fallback
            rename[col] = col.strip().lower().replace(" ", "_")
    df = df.rename(columns=rename)

    # --- Timestamp ---
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    elif "date" in df.columns and "time" in df.columns:
        df["timestamp"] = pd.to_datetime(
            df["date"].astype(str) + " " + df["time"].astype(str), errors="coerce"
        )
    else:
        df["timestamp"] = pd.Timestamp("2024-01-01")

    # --- Required column defaults ---
    defaults = {
        "is_laundering":    0,
        "laundering_type":  "",
        "payment_currency": "INR",
        "received_currency":"INR",
        "sender_bank":      "Unknown",
        "receiver_bank":    "Unknown",
        "payment_type":     "NEFT",
        "amount_received":  None,
    }
    for col, val in defaults.items():
        if col not in df.columns:
            df[col] = val

    df["is_laundering"] = pd.to_numeric(df["is_laundering"], errors="coerce").fillna(0).astype(int)
    df["laundering_type"] = df["laundering_type"].fillna("").astype(str)
    df["amount"] = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0)

    # Use amount_received if amount is zero and amount_received exists
    if "amount_received" in df.columns:
        mask = df["amount"] == 0
        df.loc[mask, "amount"] = pd.to_numeric(df.loc[mask, "amount_received"], errors="coerce").fillna(0.0)

    # Drop rows with no accounts
    df = df.dropna(subset=["sender_account", "receiver_account"])
    df["sender_account"] = df["sender_account"].astype(str).str.strip()
    df["receiver_account"] = df["receiver_account"].astype(str).str.strip()

    # --- Ring-preserving sample (optional) ---
    # A purely random sample scatters laundering rings: each laundering account
    # ends up in 1-2 sampled rows, so velocity/structuring rules can't fire and
    # Louvain has no ring structure to find. Instead we keep (a) all laundering
    # rows, (b) the surrounding activity of the accounts involved, and (c) fill
    # the rest with random clean rows.
    if sample_n is not None and len(df) > sample_n:
        pos = df[df["is_laundering"] == 1]
        launder_accs = set(pos["sender_account"]) | set(pos["receiver_account"])

        neg = df[df["is_laundering"] == 0]
        ctx_mask = (
            neg["sender_account"].isin(launder_accs)
            | neg["receiver_account"].isin(launder_accs)
        )
        context = neg[ctx_mask]
        ctx_cap = max(0, min(len(context), sample_n // 10))
        if len(context) > ctx_cap:
            context = context.sample(ctx_cap, random_state=42)

        n_fill = max(0, sample_n - len(pos) - len(context))
        fill_pool = neg[~ctx_mask]
        fill = fill_pool.sample(min(n_fill, len(fill_pool)), random_state=42)

        df = pd.concat([pos, context, fill]).sample(frac=1, random_state=42).reset_index(drop=True)
        print(f"[load_saml_d] Ring-preserving sample: {len(df)} rows "
              f"({len(pos)} laundering, {len(context)} ring-context, {len(fill)} random clean).")

    df["txn_id"] = ["TXN-" + str(i).zfill(7) for i in range(len(df))]

    launder_count = df["is_laundering"].sum()
    pct = 100 * launder_count / max(len(df), 1)
    print(f"[load_saml_d] Loaded {len(df):,} transactions — "
          f"{launder_count:,} laundering ({pct:.2f}%).")
    return df
