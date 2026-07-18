"""Regulation lookup — local semantic search, fully air-gapped.

Embeds the curated PMLA/RBI/FIU-IND corpus with nomic-embed-text through
Ollama (replacing chromadb + sentence-transformers — see change.md), caches
vectors to disk, and searches by cosine similarity in-process. If the embed
model is unavailable it degrades to keyword-overlap scoring, so regulation
citations never block the demo (SPEC card 2, pitfall 1).
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import List, Optional

from config import REGS_PATH, CACHE_DIR
from shared_contracts import RegulationRef


def _cos(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return dot / (na * nb)


def _tokenize(s: str) -> set:
    return set(re.findall(r"[a-z]{3,}", s.lower()))


class RegulationStore:
    def __init__(self, llm_client=None):
        with open(REGS_PATH, encoding="utf-8") as f:
            self.entries: List[dict] = json.load(f)
        self.llm = llm_client
        self.vectors: Optional[List[List[float]]] = None
        self._index_texts = [
            f"{e['title']}. {e['text']} {' '.join(e['tags'])}" for e in self.entries
        ]

    def ensure_index(self) -> bool:
        """Build (or load cached) embeddings. Returns True if semantic search
        is available, False if we're on the keyword fallback."""
        if self.vectors is not None:
            return True
        if self.llm is None:
            return False
        corpus_hash = hashlib.sha256(
            json.dumps(self._index_texts).encode()
        ).hexdigest()[:16]
        cache_file = CACHE_DIR / f"regs_embed_{corpus_hash}.json"
        try:
            if cache_file.exists():
                self.vectors = json.loads(cache_file.read_text())
            else:
                self.vectors = self.llm.embed(self._index_texts)
                cache_file.write_text(json.dumps(self.vectors))
            return True
        except Exception:  # noqa: BLE001 — fall back to keywords, never block
            self.vectors = None
            return False

    def search(self, query: str, k: int = 3) -> List[RegulationRef]:
        scored: List[tuple]
        if self.ensure_index() and self.vectors:
            try:
                qv = self.llm.embed([query])[0]
                scored = [(_cos(qv, v), e) for v, e in zip(self.vectors, self.entries)]
            except Exception:  # noqa: BLE001
                scored = self._keyword_scores(query)
        else:
            scored = self._keyword_scores(query)
        scored.sort(key=lambda x: x[0], reverse=True)
        out = []
        for score, e in scored[:k]:
            out.append(
                RegulationRef(
                    section=e["section"],
                    text_snippet=e["text"],
                    relevance=f"{e['title']} (match score {score:.2f})",
                )
            )
        return out

    def _keyword_scores(self, query: str) -> List[tuple]:
        q = _tokenize(query)
        scored = []
        for e, text in zip(self.entries, self._index_texts):
            overlap = len(q & _tokenize(text))
            scored.append((overlap / (len(q) or 1), e))
        return scored
