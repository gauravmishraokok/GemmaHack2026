"""Append-only, hash-chained audit log.

Every entry embeds the SHA-256 of the previous entry, so any retroactive
edit breaks the chain and is detectable by verify_chain(). This gives the
compliance officer an immutable who/what/when/evidence-refs trail without a
database — a JSONL file is deliberately boring and inspectable.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional

from config import AUDIT_LOG_PATH

GENESIS_HASH = "0" * 64


def _hash_entry(entry: Dict) -> str:
    material = json.dumps(
        {k: v for k, v in entry.items() if k != "hash"}, sort_keys=True, default=str
    )
    return hashlib.sha256(material.encode()).hexdigest()


def _read_all() -> List[Dict]:
    if not AUDIT_LOG_PATH.exists():
        return []
    entries = []
    with open(AUDIT_LOG_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def append(
    action: str,
    case_id: str,
    actor: str = "analyst",
    detail: Optional[Dict] = None,
    evidence_refs: Optional[List[str]] = None,
) -> Dict:
    entries = _read_all()
    prev_hash = entries[-1]["hash"] if entries else GENESIS_HASH
    entry = {
        "seq": len(entries) + 1,
        "ts": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "action": action,
        "case_id": case_id,
        "evidence_refs": evidence_refs or [],
        "detail": detail or {},
        "prev_hash": prev_hash,
    }
    entry["hash"] = _hash_entry(entry)
    with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")
    return entry


def entries_for_case(case_id: str) -> List[Dict]:
    return [e for e in _read_all() if e["case_id"] == case_id]


def verify_chain() -> Dict:
    entries = _read_all()
    prev = GENESIS_HASH
    for e in entries:
        if e["prev_hash"] != prev or _hash_entry(e) != e["hash"]:
            return {"intact": False, "broken_at_seq": e["seq"], "length": len(entries)}
        prev = e["hash"]
    return {"intact": True, "length": len(entries)}
