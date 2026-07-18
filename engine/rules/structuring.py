"""
Structuring rule: repeated near-threshold transactions from/to the same account pair.
Classic smurfing / structuring pattern — multiple just-below-threshold txns between same pair.
"""

import pandas as pd

THRESHOLD = 500_000
WINDOW_BELOW = 50_000
MIN_REPEAT = 2


def flag(df: pd.DataFrame, threshold: int = THRESHOLD, window_below: int = WINDOW_BELOW, min_repeat: int = MIN_REPEAT) -> pd.DataFrame:
    low = threshold - window_below
    near = df[(df["amount"] >= low) & (df["amount"] < threshold)].copy()
    near["pair"] = near["sender_account"] + "|" + near["receiver_account"]

    pair_counts = near.groupby("pair")
    alerts = []
    counter = [0]

    for pair, group in pair_counts:
        if len(group) >= min_repeat:
            src, dst = pair.split("|")
            counter[0] += 1
            alerts.append({
                "account": src,
                "alert_id": f"STR-{counter[0]:04d}",
                "rule": "structuring",
                "pair": pair,
                "count": len(group),
                "total_amount": float(group["amount"].sum()),
                "txn_ids": list(group["txn_id"]),
                "score": min(1.0, 0.5 + 0.1 * len(group)),
                "detail": f"{len(group)} near-threshold transfers to {dst} "
                          f"totalling {float(group['amount'].sum()):,.0f}, "
                          f"each just under {threshold:,.0f}",
            })

    return pd.DataFrame(alerts) if alerts else pd.DataFrame(
        columns=["account", "alert_id", "rule", "pair", "count", "total_amount", "txn_ids", "score", "detail"]
    )
