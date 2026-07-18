"""
Modular LLM client for the reasoning service.

All model access goes through `LLMClient` so the backend (Ollama today,
llama.cpp / vLLM tomorrow) can be swapped without touching the pipeline.

OllamaClient uses the OpenAI-compatible endpoint because it is the one that
returns BOTH schema-constrained JSON (response_format -> compiled to a
llama.cpp decoding grammar) and per-token logprobs in a single pass —
verified against ollama 0.32.1 + gemma4:12b.

The gemma4:12b build emits reasoning-channel tokens before the final
constrained answer, so the logprob stream is longer than the content string.
`content_token_logprobs` maps the content back onto its exact token span so
the confidence layer only scores tokens the analyst will actually read.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import requests

from config import (
    OLLAMA_URL,
    OLLAMA_MODEL,
    OLLAMA_BASE_MODEL,
    NUM_CTX,
    EMBED_MODEL,
    MAX_TOKENS,
    TEMPERATURE,
    LLM_TIMEOUT_S,
)


@dataclass
class TokenLogprob:
    token: str
    logprob: float


@dataclass
class GenerationResult:
    content: str                       # raw JSON text the model produced
    parsed: Dict[str, Any]             # parsed JSON object
    tokens: List[TokenLogprob] = field(default_factory=list)   # full stream
    content_tokens: List[TokenLogprob] = field(default_factory=list)  # answer-only span
    model: str = ""
    logprobs_available: bool = False


class LLMClient:
    """Interface. Swap implementations freely; the pipeline only calls these."""

    def generate_json(self, system: str, user: str, schema: Dict[str, Any]) -> GenerationResult:
        raise NotImplementedError

    def embed(self, texts: List[str]) -> List[List[float]]:
        raise NotImplementedError

    def health(self) -> Dict[str, Any]:
        raise NotImplementedError


def _align_content_tokens(content: str, tokens: List[TokenLogprob]) -> List[TokenLogprob]:
    """Locate the answer text inside the (reasoning + answer) token stream.

    Concatenates all token strings and rfinds the content; returns the tokens
    covering that character range. Falls back to the full stream if alignment
    fails (e.g. tokenizer byte quirks) — confidence then degrades gracefully
    rather than crashing.
    """
    if not tokens or not content:
        return tokens
    joined = "".join(t.token for t in tokens)
    start = joined.rfind(content)
    if start == -1:
        # try a shorter anchor: first 40 chars of content
        anchor = content[: min(40, len(content))]
        start = joined.rfind(anchor)
        if start == -1:
            return tokens
    end = start + len(content)
    out, pos = [], 0
    for t in tokens:
        tok_start, tok_end = pos, pos + len(t.token)
        if tok_end > start and tok_start < end:
            out.append(t)
        pos = tok_end
    return out or tokens


class OllamaClient(LLMClient):
    def __init__(self, base_url: str = OLLAMA_URL, model: str = OLLAMA_MODEL):
        self.base_url = base_url.rstrip("/")
        self.model = model

    def ensure_model(self) -> str:
        """Provision the extended-context derivative if it doesn't exist yet.

        Ollama's stock 4096-token context truncates evidence prompt +
        reasoning-channel thinking before the constrained answer begins
        (observed: finish_reason=length with empty content). /api/create
        with `from` + parameters bakes num_ctx into a derived tag that
        shares the base weights. Falls back to the base model on failure.
        """
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            r.raise_for_status()
            names = {m["name"] for m in r.json().get("models", [])}
            if self.model in names or f"{self.model}:latest" in names:
                return self.model
            r = requests.post(
                f"{self.base_url}/api/create",
                json={
                    "model": self.model,
                    "from": OLLAMA_BASE_MODEL,
                    "parameters": {"num_ctx": NUM_CTX},
                    "stream": False,
                },
                timeout=180,
            )
            r.raise_for_status()
        except Exception:  # noqa: BLE001 — degrade to base model, never block startup
            self.model = OLLAMA_BASE_MODEL
        return self.model

    def generate_json(self, system: str, user: str, schema: Dict[str, Any]) -> GenerationResult:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS,
            "logprobs": True,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "investigation", "schema": schema},
            },
        }
        r = requests.post(
            f"{self.base_url}/v1/chat/completions",
            json=payload,
            timeout=LLM_TIMEOUT_S,
        )
        r.raise_for_status()
        data = r.json()
        choice = data["choices"][0]
        content = choice["message"]["content"]
        if choice.get("finish_reason") == "length" or not content.strip():
            raise RuntimeError(
                "generation truncated before the constrained answer completed "
                f"(finish_reason={choice.get('finish_reason')}, usage={data.get('usage')}). "
                "Raise NUM_CTX / MAX_TOKENS or check the derived model provisioned."
            )
        parsed = json.loads(content)

        tokens: List[TokenLogprob] = []
        lp = choice.get("logprobs") or {}
        for entry in lp.get("content") or []:
            tokens.append(TokenLogprob(token=entry["token"], logprob=float(entry["logprob"])))

        return GenerationResult(
            content=content,
            parsed=parsed,
            tokens=tokens,
            content_tokens=_align_content_tokens(content, tokens),
            model=self.model,
            logprobs_available=bool(tokens),
        )

    def embed(self, texts: List[str]) -> List[List[float]]:
        r = requests.post(
            f"{self.base_url}/api/embed",
            json={"model": EMBED_MODEL, "input": texts},
            timeout=120,
        )
        r.raise_for_status()
        return r.json()["embeddings"]

    def health(self) -> Dict[str, Any]:
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=5)
            r.raise_for_status()
            names = [m["name"] for m in r.json().get("models", [])]
            return {
                "ollama": "up",
                "model": self.model,
                "model_available": any(n == self.model or n.split(":")[0] == self.model for n in names)
                or self.model in names,
                "embed_model_available": any(n.startswith(EMBED_MODEL) for n in names),
            }
        except Exception as e:  # noqa: BLE001 — health must never raise
            return {"ollama": "down", "model": self.model, "error": str(e)}


class MockLLMClient(LLMClient):
    """Deterministic stand-in so the API + frontend run without a GPU.

    Produces schema-valid output with varied fake logprobs so the heat-map
    still shows green/yellow/red bands during frontend development.
    """

    def generate_json(self, system: str, user: str, schema: Dict[str, Any]) -> GenerationResult:
        from serving.schemas import GOS_TAGS  # local import avoids cycle

        parsed = {
            "evidence_assessment": [
                {"ev_id": "EV-001", "observation": "Repeated transfers just below the reporting threshold."},
                {"ev_id": "EV-002", "observation": "Two source accounts share a single PAN."},
                {"ev_id": "EV-003", "observation": "All transfers target the same beneficiary within 72 hours."},
            ],
            "behaviour_pattern": "Coordinated structuring across PAN-linked accounts.",
            "evidence_sufficiency": "SUFFICIENT",
            "investigation_summary": "MOCK MODE: deterministic output for offline development. "
            "The case shows repeated sub-threshold transfers from PAN-linked accounts to one beneficiary.",
            "suggested_questions": [
                "What is the declared source of funds for the originating accounts?",
                "Is there a business relationship with the beneficiary?",
                "Were any cash deposits made before the transfers?",
            ],
            "gos_tag": GOS_TAGS[0],
            "narration": [
                "Between the review dates the subject accounts executed repeated transfers individually below the reporting threshold.",
                "The originating accounts are linked to a single PAN, indicating common control.",
                "All transfers were directed to one beneficiary account within a compressed time window.",
                "The pattern is consistent with structuring designed to avoid the prescribed reporting requirement.",
            ],
            "amounts_cited": [990000.0, 985000.0],
            "recommended_action": "FILE_STR_WITH_FIU_IND",
        }
        content = json.dumps(parsed)
        # fabricate varied logprobs so bands visibly differ in the UI
        toks = [
            TokenLogprob(token=w + " ", logprob=-0.05 - 0.9 * ((i * 2654435761) % 97) / 97.0)
            for i, w in enumerate(content.split(" "))
        ]
        return GenerationResult(
            content=content, parsed=parsed, tokens=toks, content_tokens=toks,
            model="mock", logprobs_available=True,
        )

    def embed(self, texts: List[str]) -> List[List[float]]:
        # cheap deterministic bag-of-chars embedding; good enough for mock mode
        out = []
        for t in texts:
            v = [0.0] * 64
            for i, ch in enumerate(t.lower()):
                v[(ord(ch) + i) % 64] += 1.0
            norm = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append([x / norm for x in v])
        return out

    def health(self) -> Dict[str, Any]:
        return {"ollama": "mock", "model": "mock", "model_available": True}


def sentence_confidence(
    sentence: str, content: str, content_tokens: List[TokenLogprob]
) -> Optional[float]:
    """Mean logprob of the tokens spanning `sentence` inside `content`, exp'd
    to a 0-1 probability-like score. Returns None if the span can't be found.

    `sentence` appears inside the raw JSON `content` in its escaped form, so
    search for json.dumps(sentence) minus the surrounding quotes.
    """
    if not content_tokens:
        return None
    escaped = json.dumps(sentence)[1:-1]
    start = content.find(escaped)
    if start == -1:
        return None
    end = start + len(escaped)
    pos = 0
    lps: List[float] = []
    for t in content_tokens:
        tok_start, tok_end = pos, pos + len(t.token)
        if tok_end > start and tok_start < end:
            lps.append(t.logprob)
        pos = tok_end
    if not lps:
        return None
    return math.exp(sum(lps) / len(lps))


def get_client() -> LLMClient:
    from config import MOCK_LLM

    return MockLLMClient() if MOCK_LLM else OllamaClient()
