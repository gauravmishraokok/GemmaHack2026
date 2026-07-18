"""Timeline construction — pure computation over Case.transactions."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import List

from shared_contracts import Case, TimelineEvent


def _fmt_inr(amount: float) -> str:
    """Indian digit grouping: 2455000 -> ₹24,55,000."""
    n = int(round(amount))
    s = str(n)
    if len(s) <= 3:
        grouped = s
    else:
        head, tail = s[:-3], s[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        grouped = ",".join(parts + [tail])
    return f"₹{grouped}"


# Engine emits IBM-AML full-name currencies ("US Dollar", "Euro", "Rupee"),
# not ISO codes — see integration guide §3.1.
_CURRENCY_SYMBOLS = {
    "inr": "₹", "rupee": "₹", "indian rupee": "₹",
    "usd": "$", "us dollar": "$",
    "eur": "€", "euro": "€",
    "gbp": "£", "uk pound": "£", "pound": "£",
    "yen": "¥", "jpy": "¥",
}


def format_amount(amount: float, currency: str = "INR") -> str:
    """Currency-aware formatting. Rupees keep Indian grouping; everything else
    gets western grouping with its symbol, unknown currencies keep their name."""
    key = (currency or "INR").strip().lower()
    sym = _CURRENCY_SYMBOLS.get(key)
    if sym == "₹":
        return _fmt_inr(amount)
    grouped = f"{int(round(amount)):,}"
    return f"{sym}{grouped}" if sym else f"{grouped} {currency}"


def build_timeline(case: Case) -> List[TimelineEvent]:
    txns = sorted(case.transactions, key=lambda t: t.timestamp)
    events: List[TimelineEvent] = []
    for t in txns:
        flag = f" [{t.typology_flag}]" if t.typology_flag else ""
        events.append(
            TimelineEvent(
                ts=t.timestamp,
                event=f"{t.txn_id}: {t.from_account} sent {format_amount(t.amount, t.currency)} to {t.to_account}{flag}",
            )
        )

    # Burst annotations: >=3 txns within any rolling 48h window per sender.
    by_sender = defaultdict(list)
    for t in txns:
        by_sender[t.from_account].append(t)
    for sender, ts in by_sender.items():
        for i in range(len(ts)):
            window = [x for x in ts[i:] if x.timestamp - ts[i].timestamp <= timedelta(hours=48)]
            if len(window) >= 3:
                total = sum(x.amount for x in window)
                events.append(
                    TimelineEvent(
                        ts=window[-1].timestamp,
                        event=f"VELOCITY: {sender} moved {format_amount(total, window[0].currency)} across "
                        f"{len(window)} transactions within 48h",
                    )
                )
                break  # one annotation per sender is enough signal
    events.sort(key=lambda e: e.ts)
    return events
