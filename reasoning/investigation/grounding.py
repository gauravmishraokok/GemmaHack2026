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

# Engine currencies are IBM-AML full names ("Euro", "US Dollar", "Rupee"), so
# amounts can appear as ₹9,90,000 / €990,000 / "990,000 Euro" / bare "990000".
# Three patterns, deduped by span, so no cited figure escapes verification:
#   A: currency symbol/code prefix        B: comma-grouped number
#   C: bare integer >= 5 digits (amounts; short counts/hours/years don't match)
_AMOUNT_PREFIX_RE = re.compile(
    r"(?:₹|\$|€|£|¥|rs\.?\s*|inr\s*|eur\s*|usd\s*|gbp\s*)(\d[\d,]*(?:\.\d+)?)", re.IGNORECASE
)
_AMOUNT_GROUPED_RE = re.compile(r"\b\d{1,3}(?:,\d{2,3})+(?:\.\d+)?\b")
_AMOUNT_BARE_RE = re.compile(r"\b\d{5,}(?:\.\d+)?\b")
_EVID_RE = re.compile(r"EV-\d{3}")


def _case_amounts(case: Case) -> Set[float]:
    amounts: Set[float] = set()
    for t in case.transactions:
        amounts.add(round(t.amount, 2))
        # integer-rounded citation of a decimal ledger amount is a display
        # convention, not a hallucination — accept it as grounded
        amounts.add(float(int(round(t.amount))))
    # aggregates an analyst may legitimately cite:
    # per-sender / per-receiver / per-pair totals + grand total
    amounts.add(round(sum(t.amount for t in case.transactions), 2))
    per_sender: Dict[str, float] = {}
    per_receiver: Dict[str, float] = {}
    per_pair: Dict[tuple, float] = {}
    for t in case.transactions:
        per_sender[t.from_account] = per_sender.get(t.from_account, 0) + t.amount
        per_receiver[t.to_account] = per_receiver.get(t.to_account, 0) + t.amount
        pair = (t.from_account, t.to_account)
        per_pair[pair] = per_pair.get(pair, 0) + t.amount
    amounts.update(round(v, 2) for v in per_sender.values())
    amounts.update(round(v, 2) for v in per_receiver.values())
    amounts.update(round(v, 2) for v in per_pair.values())
    # figures quoted in engine rule alerts are evidence the model may cite
    # verbatim (integration guide §3.4) — treat them as known ground truth
    for a in case.alert_details:
        amounts.update(round(v, 2) for v in _parse_sentence_amounts(a.detail))
    # same integer-rounding tolerance for aggregates
    amounts |= {float(int(round(a))) for a in list(amounts)}
    return amounts


def _parse_sentence_amounts(sentence: str) -> List[float]:
    spans_seen: List[tuple] = []
    amounts: List[float] = []

    def collect(regex, group):
        for m in regex.finditer(sentence):
            span = m.span(group)
            if any(s[0] < span[1] and span[0] < s[1] for s in spans_seen):
                continue  # already captured by a higher-priority pattern
            raw = m.group(group).replace(",", "")
            if not raw or not any(ch.isdigit() for ch in raw):
                continue
            spans_seen.append(span)
            amounts.append(float(raw))

    collect(_AMOUNT_PREFIX_RE, 1)
    collect(_AMOUNT_GROUPED_RE, 0)
    collect(_AMOUNT_BARE_RE, 0)
    return amounts


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
