"""Deterministic grounding verifier — the belt-and-braces layer on top of
constrained decoding.

The grammar guarantees *structure*; this guarantees *content*: every rupee
amount and every ev_id the model cites is checked against the actual case.
A sentence citing an unverifiable figure is hard-capped into the red band no
matter how confident the model's logprobs were — a hallucinated number must
never look trustworthy.
"""
from __future__ import annotations

import re
from typing import Dict, List, Set

from shared_contracts import Case, EvidencePack

_AMOUNT_RE = re.compile(r"(?:₹|rs\.?\s*|inr\s*)([\d,]+(?:\.\d+)?)", re.IGNORECASE)
_EVID_RE = re.compile(r"EV-\d{3}")


def _case_amounts(case: Case) -> Set[float]:
    amounts: Set[float] = set()
    for t in case.transactions:
        amounts.add(round(t.amount, 2))
    # aggregates an analyst may legitimately cite: totals per sender/receiver + grand total
    amounts.add(round(sum(t.amount for t in case.transactions), 2))
    per_sender: Dict[str, float] = {}
    per_receiver: Dict[str, float] = {}
    for t in case.transactions:
        per_sender[t.from_account] = per_sender.get(t.from_account, 0) + t.amount
        per_receiver[t.to_account] = per_receiver.get(t.to_account, 0) + t.amount
    amounts.update(round(v, 2) for v in per_sender.values())
    amounts.update(round(v, 2) for v in per_receiver.values())
    return amounts


def _parse_sentence_amounts(sentence: str) -> List[float]:
    return [float(m.replace(",", "")) for m in _AMOUNT_RE.findall(sentence)]


def ground_sentence(sentence: str, case: Case, pack: EvidencePack) -> Dict:
    """Score one narration sentence: fraction of its checkable claims
    (amounts, ev_ids) that verify against the case. No checkable claims -> 1.0
    (nothing to falsify)."""
    known_amounts = _case_amounts(case)
    known_evids = {ev.ev_id for ev in pack.evidence}

    checks = 0
    passed = 0
    violations: List[str] = []

    for amt in _parse_sentence_amounts(sentence):
        checks += 1
        if round(amt, 2) in known_amounts:
            passed += 1
        else:
            violations.append(f"amount ₹{amt:,.0f} not found in case transactions")

    for evid in _EVID_RE.findall(sentence):
        checks += 1
        if evid in known_evids:
            passed += 1
        else:
            violations.append(f"cited {evid} does not exist in the evidence pack")

    score = passed / checks if checks else 1.0
    return {"score": score, "violations": violations, "checked_claims": checks}


def verify_amounts_cited(amounts_cited: List[float], case: Case) -> List[str]:
    """Post-hoc check that every amount in the model's amounts_cited array
    exists in the case (SPEC card 2 phase C, belt-and-braces)."""
    known = _case_amounts(case)
    return [
        f"amounts_cited contains ₹{a:,.0f} which is not in case transactions"
        for a in amounts_cited
        if round(a, 2) not in known
    ]
