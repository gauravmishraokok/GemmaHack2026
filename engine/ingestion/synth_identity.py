"""
Phase 2 — Synthetic KYC/PAN generation on the consolidated dataset.

The IBM AML dataset has transactions only — no identities. This module:
  1. Finds REAL laundering rings: connected components of accounts that
     transact with each other on is_laundering=1 transactions.
  2. Gives every account in a ring the SAME synthetic PAN (one beneficial
     owner controlling many accounts), FAILED/PENDING KYC, a shared shell
     company, and High Risk jurisdiction.
  3. Gives clean accounts unique PANs, VERIFIED KYC, Individual/Registered
     Business subtype, Standard jurisdiction.
  4. Appends the fields as sender_*/receiver_* columns on the transactions
     DataFrame (the "consolidated dataset").

The Rule Engine and XGBoost never read these columns — they ride along
silently and surface only in the final case output for Person 2.
"""

import random
import string
from typing import Dict, Tuple

import networkx as nx
import pandas as pd

RNG_SEED = 42

_SHELL_COMPANY_NAMES = [
    "Orion Holdings", "Vertex Global Trading", "Meridian Exports",
    "Zenith Commerce", "Aurora Ventures", "Pinnacle Trade Links",
    "Cascade Enterprises", "Summit Overseas", "Nimbus Trading Co",
    "Equinox Impex", "Helix Commodities", "Polaris Mercantile",
]

_FIRST_NAMES = [
    "Arjun", "Priya", "Rahul", "Sneha", "Vikram", "Anita", "Karan", "Meera",
    "Rohan", "Divya", "Amit", "Pooja", "Sanjay", "Neha", "Rajesh", "Kavita",
]
_LAST_NAMES = [
    "Sharma", "Verma", "Patel", "Gupta", "Singh", "Mehta", "Iyer", "Reddy",
    "Kapoor", "Joshi", "Nair", "Malhotra", "Chopra", "Desai", "Rao", "Bose",
]

KYC_FIELDS = [
    "pan", "kyc_status", "entity_subtype", "jurisdiction",
    "linked_company", "holder_name",
]


def _make_pan(rng: random.Random) -> str:
    """Realistic PAN format: 5 letters + 4 digits + 1 letter, e.g. AABCX1234F."""
    letters = "".join(rng.choices(string.ascii_uppercase, k=5))
    digits = "".join(rng.choices(string.digits, k=4))
    return f"{letters}{digits}{rng.choice(string.ascii_uppercase)}"


def find_laundering_rings(df: pd.DataFrame, min_ring_size: int = 2, max_rings: int = 40) -> list:
    """
    Connected components of the graph whose edges are is_laundering=1
    transactions. These are the real rings present in the data.
    Largest rings first; capped so identity generation stays fast.
    """
    launder = df[df["is_laundering"] == 1]
    if launder.empty:
        return []

    g = nx.Graph()
    g.add_edges_from(zip(launder["sender_account"], launder["receiver_account"]))
    rings = [sorted(c) for c in nx.connected_components(g) if len(c) >= min_ring_size]
    rings.sort(key=len, reverse=True)
    return rings[:max_rings]


def build_kyc_records(df: pd.DataFrame) -> Tuple[Dict[str, Dict], list]:
    """
    Returns (kyc: {account -> record}, rings).
    Ring accounts share a PAN + shell company; clean accounts get unique,
    verified identities.
    """
    rng = random.Random(RNG_SEED)
    rings = find_laundering_rings(df)

    kyc: Dict[str, Dict] = {}
    for ring_idx, ring in enumerate(rings):
        shared_pan = _make_pan(rng)
        shell_co = f"{_SHELL_COMPANY_NAMES[ring_idx % len(_SHELL_COMPANY_NAMES)]} Pvt Ltd"
        for acc in ring:
            kyc[acc] = {
                "pan":            shared_pan,
                "kyc_status":     rng.choice(["FAILED", "FAILED", "PENDING"]),
                "entity_subtype": "Shell Company",
                "jurisdiction":   "High Risk",
                "linked_company": shell_co,
                "holder_name":    f"{rng.choice(_FIRST_NAMES)} {rng.choice(_LAST_NAMES)}",
            }

    all_accounts = pd.unique(
        pd.concat([df["sender_account"], df["receiver_account"]], ignore_index=True)
    )
    for acc in all_accounts:
        if acc in kyc:
            continue
        kyc[acc] = {
            "pan":            _make_pan(rng),
            "kyc_status":     "VERIFIED",
            "entity_subtype": rng.choice(["Individual", "Individual", "Individual", "Registered Business"]),
            "jurisdiction":   "Standard",
            "linked_company": None,
            "holder_name":    f"{rng.choice(_FIRST_NAMES)} {rng.choice(_LAST_NAMES)}",
        }

    n_ring_accounts = sum(len(r) for r in rings)
    print(f"[kyc] {len(rings)} laundering rings ({n_ring_accounts} accounts) "
          f"given shared PANs; {len(kyc) - n_ring_accounts} clean accounts.")
    return kyc, rings


def consolidate(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, Dict]]:
    """
    Append KYC columns to the transactions DataFrame.
    Returns (consolidated_df, kyc_records).
    """
    kyc, _rings = build_kyc_records(df)

    for side in ("sender", "receiver"):
        mapped = df[f"{side}_account"].map(kyc)
        for field in KYC_FIELDS:
            df[f"{side}_{field}"] = mapped.map(
                lambda r, f=field: r.get(f) if isinstance(r, dict) else None
            )

    return df, kyc
