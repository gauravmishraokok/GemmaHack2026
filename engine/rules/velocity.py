"""
Velocity rule: flag accounts with >N transactions in a rolling window.
Returns a DataFrame of (account, alert_id, rule, count, window_hours).
"""

import pandas as pd
from typing import List


VELOCITY_THRESHOLD = 5     # txns in window
WINDOW_HOURS = 48


def flag(df: pd.DataFrame, threshold: int = VELOCITY_THRESHOLD, window_hours: int = WINDOW_HOURS) -> pd.DataFrame:
    """
    For each account (sender), check if they sent more than `threshold`
    transactions within any rolling `window_hours`-hour window.
    Returns alert rows with columns: account, alert_id, rule, txn_ids.
    """
    df = df.sort_values("timestamp").copy()
    alerts = []
    alert_counter = [0]

    for account, group in df.groupby("sender_account"):
        group = group.sort_values("timestamp")
        times = group["timestamp"].values
        txn_ids = group["txn_id"].values
        n = len(times)
        window_ns = pd.Timedelta(hours=window_hours).value

        for i in range(n):
            window_mask = (times >= times[i]) & (times <= times[i] + window_ns)
            count = int(window_mask.sum())
            if count >= threshold:
                alert_counter[0] += 1
                total = float(group.loc[window_mask, "amount"].sum()) if "amount" in group.columns else 0.0
                alerts.append({
                    "account": account,
                    "alert_id": f"VEL-{alert_counter[0]:04d}",
                    "rule": "velocity",
                    "count": count,
                    "window_hours": window_hours,
                    "txn_ids": list(txn_ids[window_mask]),
                    "score": min(1.0, count / (threshold * 2)),
                    "detail": f"{count} outbound transactions within a {window_hours}h window "
                              f"totalling {total:,.0f}",
                })
                break  # one alert per account per pass

    return pd.DataFrame(alerts) if alerts else pd.DataFrame(
        columns=["account", "alert_id", "rule", "count", "window_hours", "txn_ids", "score", "detail"]
    )
