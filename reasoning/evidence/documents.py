"""Document evidence — STUBBED (SPEC card 2 phase B).

Simulates a Gemma-vision extraction pass over scanned KYC/invoices using
fixtures. Honest by design: every item carries extracted_by="gemma-vision
(stubbed)" and the write-up says so.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Dict, List

from config import DOCS_PATH


@lru_cache(maxsize=1)
def _load() -> Dict[str, List[dict]]:
    with open(DOCS_PATH, encoding="utf-8") as f:
        data = json.load(f)
    data.pop("_note", None)
    return data


def documents_for_accounts(account_ids: List[str]) -> List[dict]:
    docs = _load()
    out: List[dict] = []
    for acc in account_ids:
        for d in docs.get(acc, []):
            out.append({**d, "account": acc})
    return out
