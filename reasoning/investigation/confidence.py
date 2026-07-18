"""Confidence layer: fuses the model's own token logprobs with deterministic
grounding into per-sentence bands.

  lm_conf    = exp(mean logprob of the sentence's tokens)   # model's belief
  grounding  = fraction of checkable claims that verify     # external truth
  confidence = lm_conf * (0.4 + 0.6 * grounding)

A sentence with any grounding violation is additionally capped below the red
threshold: an unverifiable figure must never render green, regardless of how
fluent the model felt while writing it.
"""
from __future__ import annotations

from typing import List, Optional

from config import GREEN_BAND, YELLOW_BAND
from shared_contracts import Case, EvidencePack, NarrationSentence
from serving.llm_client import GenerationResult, sentence_confidence
from investigation.grounding import ground_sentence

RED_CAP = 0.45  # any grounding violation forces at most this


def band_of(conf: float) -> str:
    if conf > GREEN_BAND:
        return "green"
    if conf >= YELLOW_BAND:
        return "yellow"
    return "red"


def score_narration(
    sentences: List[str],
    gen: GenerationResult,
    case: Case,
    pack: EvidencePack,
) -> List[NarrationSentence]:
    out: List[NarrationSentence] = []
    for s in sentences:
        lm_conf: Optional[float] = sentence_confidence(s, gen.content, gen.content_tokens)
        if lm_conf is None:
            lm_conf = 0.6  # alignment failed -> honest middling prior, not fake certainty

        g = ground_sentence(s, case, pack)
        conf = lm_conf * (0.4 + 0.6 * g["score"])
        if g["violations"]:
            conf = min(conf, RED_CAP)
        conf = max(0.0, min(1.0, conf))
        out.append(NarrationSentence(sentence=s, confidence=round(conf, 3), band=band_of(conf)))
    return out


def overall_confidence(narration: List[NarrationSentence]) -> float:
    if not narration:
        return 0.0
    return round(sum(n.confidence for n in narration) / len(narration), 3)
