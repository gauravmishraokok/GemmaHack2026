"""
Phase 3 — Rule engine orchestrator (coarse behavioral first pass).

Runs the three detectors on TRANSACTION columns only (KYC columns are
never read), and returns:
  flagged_accounts   — set of account ids that triggered >=1 rule
  alerts_df          — one row per alert: account, alert_id, rule, detail, txn_ids
  candidate_txns     — all rows of the consolidated df touching a flagged
                       account (full row kept — KYC rides along unused)

alerts are evidence, not a filter: they're carried to the final case output
for Person 2 to cite. Filtering happens by account via candidate_txns.
"""

from typing import Dict, Set, Tuple

import pandas as pd

from engine.rules import velocity, threshold, structuring

# Rule -> lowercase typology_flag (contract §3.1) for the txns that caused the alert
RULE_TYPOLOGY = {
    "structuring": "structuring",
    "threshold":   "structuring",
    "velocity":    "smurfing",
}


def run_rules(df: pd.DataFrame) -> Tuple[Set[str], pd.DataFrame, Dict[str, str]]:
    """
    Returns (flagged_accounts, alerts_df, txn_typology).
    txn_typology maps txn_id -> lowercase typology flag.
    """
    frames = []
    for detector in (velocity, threshold, structuring):
        alerts = detector.flag(df)
        if not alerts.empty:
            frames.append(alerts)

    if frames:
        alerts_df = pd.concat(frames, ignore_index=True)
        # One account can trigger the same rule repeatedly — keep first per (account, rule)
        alerts_df = alerts_df.drop_duplicates(subset=["account", "rule"], keep="first")
    else:
        alerts_df = pd.DataFrame(columns=["account", "alert_id", "rule", "detail", "txn_ids", "score"])

    flagged_accounts = set(alerts_df["account"]) if not alerts_df.empty else set()
    print(f"[rules] {len(alerts_df)} alerts across {len(flagged_accounts)} flagged accounts.")

    # Typology map: txns that caused an alert get the rule's typology
    txn_typology: Dict[str, str] = {}
    for _, alert in alerts_df.iterrows():
        typ = RULE_TYPOLOGY.get(alert["rule"])
        for txn_id in (alert.get("txn_ids") or []):
            txn_typology.setdefault(txn_id, typ)

    return flagged_accounts, alerts_df, txn_typology
