"""
Phase 5 — Graph construction.

Two graphs from the same confirmed transactions:

  build_txn_graph()  — transaction-only graph used for CLUSTERING.
                       Nodes: accounts. Edges: confirmed suspicious txns,
                       weight = xgb_score. NO synthetic identity edges —
                       Louvain must group accounts by real money movement,
                       not by signals we invented in Phase 2.

  Identity edges (LINKED_PAN to the PAN node) are added later, per case, at
  assembly/persistence time — storage and evidence only, never clustering.
"""

import networkx as nx
import pandas as pd


def build_txn_graph(confirmed_txns: pd.DataFrame) -> nx.Graph:
    """
    Undirected weighted graph over confirmed suspicious transactions.
    Parallel transactions between a pair aggregate their xgb_scores into
    one edge weight (stronger repeated suspicious flow = stronger tie).
    """
    g = nx.Graph()
    for src, dst, score in zip(
        confirmed_txns["sender_account"],
        confirmed_txns["receiver_account"],
        confirmed_txns["xgb_score"],
    ):
        if src == dst:
            continue
        w = float(score)
        if g.has_edge(src, dst):
            g[src][dst]["weight"] += w
        else:
            g.add_edge(src, dst, weight=w)
    return g
