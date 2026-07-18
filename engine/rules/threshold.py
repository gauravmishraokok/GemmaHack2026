"""
Threshold rule: flag transactions clustering just under known reporting thresholds.
India: CTR threshold = ₹10,00,000 (10L); STR attention threshold ~₹5,00,000 (5L).
"""

import pandas as pd

# (threshold_value, window_below) — flag txns in [threshold - window, threshold)
REPORTING_THRESHOLDS = [
    (500_000, 30_000),   # just under 5L
    (1_000_000, 50_000), # just under 10L
    (2_500_000, 100_000),
]


def flag(df: pd.DataFrame) -> pd.DataFrame:
    alerts = []
    counter = [0]

    for threshold_val, window_below in REPORTING_THRESHOLDS:
        low = threshold_val - window_below
        mask = (df["amount"] >= low) & (df["amount"] < threshold_val)
        hits = df[mask]
        for _, row in hits.iterrows():
            counter[0] += 1
            alerts.append({
                "account": row["sender_account"],
                "alert_id": f"THR-{counter[0]:04d}",
                "rule": "threshold",
                "amount": row["amount"],
                "threshold": threshold_val,
                "txn_ids": [row["txn_id"]],
                "score": 0.6 + 0.3 * ((row["amount"] - low) / window_below),
                "detail": f"Transfer of {row['amount']:,.0f} to {row['receiver_account']} "
                          f"just under the {threshold_val:,.0f} reporting threshold",
            })

    return pd.DataFrame(alerts) if alerts else pd.DataFrame(
        columns=["account", "alert_id", "rule", "amount", "threshold", "txn_ids", "score", "detail"]
    )
