"""Relationship mining — pure Python over Case.graph_edges / Case.entities.

Surfaces the patterns an analyst hunts for by hand:
  shared_director   one person directing multiple companies in the case
  linked_pan        multiple accounts hanging off one PAN
  repeat_beneficiary  same target account receiving from a sender repeatedly
  circular_flow     funds returning to the originator via a SENT-edge cycle
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Set

from shared_contracts import Case, Relationship


def _find_cycles(adj: Dict[str, Set[str]]) -> List[List[str]]:
    """Simple DFS cycle finder over the SENT digraph; returns unique cycles
    (rotation-normalized). Case subgraphs are tiny, so no need for Johnson's."""
    cycles: Set[tuple] = set()

    def dfs(start: str, node: str, path: List[str]) -> None:
        for nxt in adj.get(node, ()):  # noqa: B905
            if nxt == start and len(path) >= 2:
                cyc = path[:]
                # normalize rotation so A->B->C == B->C->A
                m = cyc.index(min(cyc))
                cycles.add(tuple(cyc[m:] + cyc[:m]))
            elif nxt not in path and len(path) < 6:
                dfs(start, nxt, path + [nxt])

    for n in list(adj):
        dfs(n, n, [n])
    return [list(c) for c in cycles]


def extract_relationships(case: Case) -> List[Relationship]:
    rels: List[Relationship] = []

    # shared_director: DIRECTOR_OF edges grouped by person
    director_targets = defaultdict(list)
    for e in case.graph_edges:
        if e.relation == "DIRECTOR_OF":
            director_targets[e.source].append(e.target)
    for person, companies in director_targets.items():
        if len(companies) >= 2:
            rels.append(Relationship(type="shared_director", entities=[person, *sorted(companies)]))

    # linked_pan: three independent sources, unioned by PAN.
    #   1. explicit engine field Case.shared_pan_groups (strongest — the engine
    #      already grouped ring accounts by beneficial owner);
    #   2. LINKED_PAN graph edges;
    #   3. entities[].owner_pan on Account nodes (fixture path / fallback).
    pan_accounts = defaultdict(set)
    for grp in case.shared_pan_groups:
        pan_accounts[f"PAN-{grp.pan}"].update(grp.accounts)
    for e in case.graph_edges:
        if e.relation == "LINKED_PAN":
            pan_accounts[e.target].add(e.source)
    for ent in case.entities:
        if ent.type == "Account" and ent.owner_pan:
            pan_accounts[f"PAN-{ent.owner_pan}"].add(ent.id)
    for pan, accounts in pan_accounts.items():
        if len(accounts) >= 2:
            rels.append(Relationship(type="linked_pan", entities=[pan, *sorted(accounts)]))

    # repeat_beneficiary: same (sender -> receiver) pair >= 2 txns
    pair_counts = defaultdict(int)
    for t in case.transactions:
        pair_counts[(t.from_account, t.to_account)] += 1
    for (src, dst), n in pair_counts.items():
        if n >= 2:
            rels.append(Relationship(type="repeat_beneficiary", entities=[src, dst]))

    # funnel: one receiver, many distinct senders
    receiver_senders = defaultdict(set)
    for t in case.transactions:
        receiver_senders[t.to_account].add(t.from_account)
    for dst, senders in receiver_senders.items():
        if len(senders) >= 4:
            rels.append(Relationship(type="funnel_account", entities=[dst, *sorted(senders)]))

    # circular_flow over SENT edges
    adj: Dict[str, Set[str]] = defaultdict(set)
    for e in case.graph_edges:
        if e.relation == "SENT":
            adj[e.source].add(e.target)
    for cyc in _find_cycles(adj):
        rels.append(Relationship(type="circular_flow", entities=cyc))

    # de-dup (type + entity set)
    seen, out = set(), []
    for r in rels:
        key = (r.type, tuple(sorted(r.entities)))
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out
