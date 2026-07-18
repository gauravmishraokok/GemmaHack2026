"""
SentinelAI reasoning service configuration.

Everything is env-var driven so integration day is a config change, not a
code change ("swap the wire, not the code" — SPEC card 3).
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# --- Ollama (local, air-gapped) -------------------------------------------
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
# Base model tag as installed locally (`ollama list`). The 4B build is fast
# enough for live demos; set OLLAMA_BASE_MODEL=gemma4:12b for deeper reasoning
# when latency doesn't matter.
OLLAMA_BASE_MODEL = os.getenv("OLLAMA_BASE_MODEL", "gemma4:latest")
# Ollama's default 4096-token context is too small for evidence prompt +
# reasoning-channel thinking + constrained answer, so at startup the service
# derives OLLAMA_MODEL from the base with num_ctx baked in (shares weights,
# no extra disk). Set OLLAMA_MODEL to an existing tag to skip provisioning.
# 16k fits fully on GPU for the 4B base (small KV cache) and covers the real
# engine hero cases (~4.3k-token evidence prompts + reasoning + answer). If you
# switch OLLAMA_BASE_MODEL to the 12B, drop this to 8192 or expect CPU offload.
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "gemma4-sentinel")
NUM_CTX = int(os.getenv("NUM_CTX", "16384"))
# Local embedding model for regulation semantic search (already in ollama list).
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
# Generation budget. The 12B build emits reasoning-channel tokens before the
# constrained JSON answer, so this must cover thinking + answer.
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "5000"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.2"))
LLM_TIMEOUT_S = int(os.getenv("LLM_TIMEOUT_S", "600"))

# Set SENTINEL_MOCK_LLM=1 to run the whole service without Ollama
# (frontend development / CI). Clearly surfaced in /health.
MOCK_LLM = os.getenv("SENTINEL_MOCK_LLM", "0") == "1"

# --- Engine integration (Person 1) ----------------------------------------
# When unset -> serve cases from fixtures/mock_cases.json.
# When set (e.g. http://localhost:8001) -> proxy GET /cases* to the engine.
ENGINE_API_URL = os.getenv("ENGINE_API_URL", "").rstrip("/")

# --- Paths ------------------------------------------------------------------
FIXTURES_DIR = BASE_DIR / "fixtures"
MOCK_CASES_PATH = FIXTURES_DIR / "mock_cases.json"
REGS_PATH = FIXTURES_DIR / "regs" / "regulations.json"
DOCS_PATH = FIXTURES_DIR / "sample_docs" / "docs.json"
CACHE_DIR = BASE_DIR / ".cache"
AUDIT_LOG_PATH = BASE_DIR / ".audit" / "audit_chain.jsonl"
EXPORT_DIR = BASE_DIR / ".exports"

for d in (CACHE_DIR, AUDIT_LOG_PATH.parent, EXPORT_DIR):
    d.mkdir(parents=True, exist_ok=True)

# --- Risk banding (assumption until Person 1's threshold endpoint is live) --
RED_THRESHOLD = 0.7
YELLOW_THRESHOLD = 0.4

# --- Confidence bands (SPEC card 2, phase C) --------------------------------
GREEN_BAND = 0.75
YELLOW_BAND = 0.50
