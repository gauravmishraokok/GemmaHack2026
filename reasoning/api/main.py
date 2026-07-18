"""SentinelAI reasoning service — FastAPI app (port 8002).

Contract endpoints (SPEC card 2 §7) return shared_contracts models exactly.
Extra endpoints (/investigate/{id}/full, /schema/str, /audit/*) serve the
frontend richer views without touching the frozen contract.
"""
from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import config
from shared_contracts import (
    Case,
    CaseSummary,
    EvidencePack,
    InvestigationResult,
    RegulationRef,
    STRDraft,
)
from serving.llm_client import get_client
from serving.schemas import GOS_TAGS, INVESTIGATION_SCHEMA, RECOMMENDED_ACTIONS
from evidence.builder import build_evidence_pack
from evidence.regulations import RegulationStore
from investigation.pipeline import investigate
from export.fiu_xml import build_str_xml
from export import audit_log
from api.case_store import CaseStore

app = FastAPI(
    title="SentinelAI — Reasoning & Investigation Service",
    version="1.0.0",
    description="Evidence construction, Gemma reasoning under constrained decoding, "
    "confidence heat-map, STR drafting, FIU export. Air-gapped by design.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

llm = get_client()
if hasattr(llm, "ensure_model"):
    llm.ensure_model()  # provision the extended-context gemma4 derivative
case_store = CaseStore()
reg_store = RegulationStore(llm_client=llm)

# In-memory cache: a 12B generation is expensive; the frontend's tabs reuse it.
_investigations: Dict[str, Dict[str, Any]] = {}


def _resolve_case(case_id: str, body: Optional[Case]) -> Case:
    if body is not None:
        return body
    case = case_store.get_case(case_id)
    if case is None:
        raise HTTPException(404, f"Unknown case_id {case_id} (source: {case_store.source})")
    return case


# ---------------------------------------------------------------- health ----
@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "reasoning",
        "case_source": case_store.source,
        "mock_llm": config.MOCK_LLM,
        "llm": llm.health(),
        "audit_chain": audit_log.verify_chain(),
    }


# ----------------------------------------------------------------- cases ----
@app.get("/cases", response_model=List[CaseSummary])
def list_cases(threshold: Optional[float] = Query(None, ge=0, le=1)):
    return case_store.list_summaries(threshold)


@app.get("/cases/{case_id}", response_model=Case)
def get_case(case_id: str):
    case = case_store.get_case(case_id)
    if case is None:
        raise HTTPException(404, f"Unknown case_id {case_id}")
    return case


# -------------------------------------------------------------- evidence ----
@app.post("/evidence/{case_id}", response_model=EvidencePack)
def evidence(case_id: str, body: Optional[Case] = Body(default=None)):
    case = _resolve_case(case_id, body)
    pack = build_evidence_pack(case, reg_store)
    audit_log.append("EVIDENCE_ASSEMBLED", case_id, actor="system",
                     detail={"items": len(pack.evidence), "missing": pack.missing_evidence})
    return pack


# ----------------------------------------------------------- investigate ----
@app.post("/investigate/{case_id}", response_model=InvestigationResult)
def run_investigation(case_id: str, body: Optional[Case] = Body(default=None)):
    case = _resolve_case(case_id, body)
    t0 = time.time()
    try:
        result, pack, diag = investigate(case, llm, reg_store)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(
            503,
            f"Investigation failed ({type(e).__name__}: {e}). "
            f"Is Ollama serving {config.OLLAMA_MODEL} at {config.OLLAMA_URL}?",
        ) from e
    diag["elapsed_s"] = round(time.time() - t0, 1)
    _investigations[case_id] = {
        "result": result.model_dump(mode="json"),
        "evidence": pack.model_dump(mode="json"),
        "diagnostics": diag,
    }
    audit_log.append(
        "INVESTIGATION_RUN", case_id, actor="system",
        detail={"status": result.status, "model": diag.get("model"),
                "elapsed_s": diag["elapsed_s"],
                "overall_confidence": diag.get("overall_confidence")},
        evidence_refs=[ev.ev_id for ev in pack.evidence],
    )
    return result


@app.get("/investigate/{case_id}/full")
def get_full_investigation(case_id: str):
    """Frontend view: result + evidence pack + diagnostics from the last run."""
    if case_id not in _investigations:
        raise HTTPException(404, "No investigation has been run for this case yet")
    return _investigations[case_id]


# ------------------------------------------------------------ regulations ----
@app.get("/regulations/search", response_model=List[RegulationRef])
def regulations_search(q: str = Query(..., min_length=2), k: int = Query(3, ge=1, le=10)):
    return reg_store.search(q, k=k)


# ---------------------------------------------------------------- export ----
class ExportResponse(BaseModel):
    xml: str
    audit_entry: Dict[str, Any]


@app.post("/export/{case_id}", response_model=ExportResponse)
def export_str(case_id: str, draft: STRDraft, actor: str = Query("analyst")):
    if draft.case_id != case_id:
        raise HTTPException(422, "case_id in path and STRDraft body disagree")
    xml = build_str_xml(draft, attested_by=actor)
    out_path = config.EXPORT_DIR / f"STR_{case_id}.xml"
    out_path.write_text(xml, encoding="utf-8")
    entry = audit_log.append(
        "STR_ATTESTED_AND_EXPORTED", case_id, actor=actor,
        detail={"gos_tag": draft.gos_tag, "sentences": len(draft.narration),
                "file": str(out_path)},
        evidence_refs=draft.evidence_refs,
    )
    return ExportResponse(xml=xml, audit_entry=entry)


# ----------------------------------------------------------------- audit ----
@app.get("/audit/verify")
def audit_verify():
    return audit_log.verify_chain()


@app.get("/audit/{case_id}")
def audit_for_case(case_id: str):
    return audit_log.entries_for_case(case_id)


# --------------------------------------------------- constrained decoding ----
@app.get("/schema/str")
def get_schema():
    """The exact JSON schema Ollama compiles into the decoding grammar."""
    return {
        "schema": INVESTIGATION_SCHEMA,
        "gos_tags": GOS_TAGS,
        "recommended_actions": RECOMMENDED_ACTIONS,
    }


class GrammarProbe(BaseModel):
    raw: str


@app.post("/grammar/validate")
def grammar_validate(probe: GrammarProbe):
    """Powers the live-reject demo widget: shows what the decoding grammar
    would refuse to ever emit. (During real generation these states are
    unreachable — invalid tokens are masked before sampling. This endpoint
    replays the same schema checks on pasted text so the audience can see
    the boundary.)"""
    errors: List[str] = []
    try:
        obj = json.loads(probe.raw)
    except json.JSONDecodeError as e:
        return {"valid": False, "error": f"not valid JSON: {e}", "checks_failed": ["json_parse"]}

    if not isinstance(obj, dict):
        return {"valid": False, "error": "top level must be an object", "checks_failed": ["type"]}

    checks_failed = []
    for key in INVESTIGATION_SCHEMA["required"]:
        if key not in obj:
            errors.append(f"missing required field '{key}'")
            checks_failed.append(f"required:{key}")
    for key in obj:
        if key not in INVESTIGATION_SCHEMA["properties"]:
            errors.append(f"field '{key}' is not in the schema (additionalProperties: false)")
            checks_failed.append(f"additional:{key}")
    if "gos_tag" in obj and obj["gos_tag"] not in GOS_TAGS:
        errors.append(
            f"gos_tag '{obj['gos_tag']}' is outside the closed FIU dictionary — "
            "under constrained decoding these tokens are unreachable"
        )
        checks_failed.append("enum:gos_tag")
    if "recommended_action" in obj and obj["recommended_action"] not in RECOMMENDED_ACTIONS:
        errors.append(f"recommended_action '{obj['recommended_action']}' is outside the closed action set")
        checks_failed.append("enum:recommended_action")
    if "narration" in obj and isinstance(obj["narration"], list):
        n = len(obj["narration"])
        if not 4 <= n <= 8:
            errors.append(f"narration must contain 4-8 sentences, got {n}")
            checks_failed.append("narration:length")

    if errors:
        return {"valid": False, "error": "; ".join(errors), "checks_failed": checks_failed}
    return {"valid": True, "error": None, "checks_failed": []}
