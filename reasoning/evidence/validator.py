"""Evidence validator — the hard gate (SPEC card 2, phase B).

If any critical evidence slot is unbacked, the pipeline stops here and
returns INSUFFICIENT_EVIDENCE. No STR is ever drafted past a failed gate;
this is a real safety property, not demo theatre.
"""
from __future__ import annotations

from typing import List, Tuple

from shared_contracts import EvidencePack

# (human-readable slot, predicate over the pack)
CRITICAL_SLOTS = [
    (
        "transaction_pattern",
        lambda p: sum(1 for ev in p.evidence if ev.kind == "transaction") >= 3,
        "at least 3 transactions establishing a pattern",
    ),
    (
        "relationship",
        lambda p: len(p.relationships) >= 1,
        "at least one entity relationship (linked PAN / shared director / repeat beneficiary / circular flow)",
    ),
    (
        "regulation_citation",
        lambda p: len(p.regulations) >= 1,
        "at least one regulation citation backing the suspicion",
    ),
    (
        "source_refs",
        lambda p: all(ev.source_ref for ev in p.evidence),
        "every evidence item traceable to a source_ref",
    ),
]


def validate(pack: EvidencePack) -> Tuple[bool, List[str]]:
    """Returns (is_sufficient, missing_descriptions)."""
    missing = []
    if not pack.evidence:
        missing.append("no evidence items at all")
    for name, predicate, description in CRITICAL_SLOTS:
        if not predicate(pack):
            missing.append(f"{name}: requires {description}")
    return (len(missing) == 0, missing)
