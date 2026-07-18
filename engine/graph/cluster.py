"""
Phase 6 — Louvain clustering + case assembly.

Louvain partitions the transaction-only graph into communities; each
community becomes one case. Because Louvain produces a PARTITION, every
account belongs to exactly one community — and each case only keeps
transactions whose BOTH endpoints are inside the community, so every
transaction lands in exactly one case (no cross-case duplication).

Case assembly enriches each community with:
  - internal confirmed transactions (each carrying its xgb_score + typology)
  - KYC entity records for every account (from Phase 2's synthetic_kyc)
  - shared_pan_groups: accounts in the case sharing one PAN (headline evidence)
  - rule alerts filtered to the case's accounts
  - a continuous training label: fraction of transaction VALUE that is
    ground-truth laundering (probe training only — never sent to Person 2)

Size caps keep cases investigable: top MAX_TXNS transactions by xgb_score,
top MAX_ENTITIES accounts by involvement.
"""

from collections import defaultdict
from typing import Dict, List

import networkx as nx
import pandas as pd

LOUVAIN_SEED = 42
MIN_COMMUNITY_SIZE = 2
MAX_TXNS = 50
MAX_ENTITIES = 30


def detect_communities(g: nx.Graph, seed: int = LOUVAIN_SEED) -> List[List[str]]:
    """Louvain on the weighted transaction graph. Largest communities first."""
    if g.number_of_nodes() == 0:
        return []
    communities = nx.algorithms.community.louvain_communities(g, weight="weight", seed=seed)
    result = [sorted(c) for c in communities if len(c) >= MIN_COMMUNITY_SIZE]
    result.sort(key=len, reverse=True)
    return result


def communities_to_cases(
    communities: List[List[str]],
    confirmed_txns: pd.DataFrame,
    alerts_df: pd.DataFrame,
    kyc: Dict[str, Dict],
) -> List[Dict]:
    """Assemble raw case dicts (internal pipeline representation)."""
    cases = []
    case_num = 0

    for comm in communities:
        comm_set = set(comm)

        # Internal transactions only — both endpoints inside the community
        mask = (
            confirmed_txns["sender_account"].isin(comm_set)
            & confirmed_txns["receiver_account"].isin(comm_set)
        )
        case_txns = confirmed_txns[mask]
        if case_txns.empty:
            continue

        # Size cap: keep the most suspicious transactions
        if len(case_txns) > MAX_TXNS:
            case_txns = case_txns.nlargest(MAX_TXNS, "xgb_score")
        case_txns = case_txns.copy()

        # Accounts actually present in the kept transactions (contract §4:
        # accounts must equal the set appearing in from/to)
        accounts = sorted(
            set(case_txns["sender_account"]) | set(case_txns["receiver_account"])
        )
        if len(accounts) > MAX_ENTITIES:
            involvement = pd.concat(
                [case_txns["sender_account"], case_txns["receiver_account"]]
            ).value_counts()
            keep = set(involvement.head(MAX_ENTITIES).index)
            mask2 = (
                case_txns["sender_account"].isin(keep)
                & case_txns["receiver_account"].isin(keep)
            )
            case_txns = case_txns[mask2].copy()
            if case_txns.empty:
                continue
            accounts = sorted(
                set(case_txns["sender_account"]) | set(case_txns["receiver_account"])
            )

        # Shared PAN groups — the headline evidence
        pan_to_accounts = defaultdict(list)
        for acc in accounts:
            pan = (kyc.get(acc) or {}).get("pan")
            if pan:
                pan_to_accounts[pan].append(acc)
        shared_pan_groups = [
            {"pan": pan, "accounts": accs}
            for pan, accs in pan_to_accounts.items() if len(accs) >= 2
        ]

        # Rule alerts for this case's accounts
        if not alerts_df.empty:
            case_alerts = alerts_df[alerts_df["account"].isin(accounts)]
            member_alert_ids = case_alerts["alert_id"].tolist()
            alert_details = [
                {"account": a["account"], "alert_type": a["rule"], "detail": a.get("detail", "")}
                for _, a in case_alerts.iterrows()
            ]
        else:
            member_alert_ids, alert_details = [], []

        # Continuous training label: laundering fraction of transaction value
        if "is_laundering" in case_txns.columns:
            total = float(case_txns["amount"].sum())
            launder = float(case_txns.loc[case_txns["is_laundering"] == 1, "amount"].sum())
            label = launder / total if total > 0 else float(case_txns["is_laundering"].any())
        else:
            label = 0.0

        case_num += 1
        cases.append({
            "case_id":           f"CASE-{case_num:06d}",
            "accounts":          accounts,
            "transactions":      case_txns,
            "member_alert_ids":  member_alert_ids,
            "alert_details":     alert_details,
            "shared_pan_groups": shared_pan_groups,
            "kyc":               {acc: kyc.get(acc, {}) for acc in accounts},
            "label":             label,
        })

    return cases
