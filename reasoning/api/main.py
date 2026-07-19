"""viGEMMAlya reasoning service — FastAPI app (port 8002).

Contract endpoints (SPEC card 2 §7) return shared_contracts models exactly.
Extra endpoints (/investigate/{id}/full, /schema/str, /audit/*) serve the
frontend richer views without touching the frozen contract.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Dict, List, Optional

from fastapi import Body, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
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
from export.notify import notify_export
from api.case_store import CaseStore
from api.events import bus

app = FastAPI(
    title="viGEMMAlya — Reasoning & Investigation Service",
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


# -------------------------------------------------------- live pipeline ----
@app.get("/events/stream")
async def events_stream(request: Request, case_id: Optional[str] = Query(None)):
    """Server-Sent Events feed of real pipeline stage transitions.

    Powers the frontend's live pipeline visualization — every event here is
    published from investigation/pipeline.py as the actual investigate() call
    progresses through evidence build -> gate -> Gemma -> grounding ->
    confidence, not a simulated/timed animation. Optionally filter to one
    case_id; omit it to watch every investigation running on this server.
    """
    q = bus.subscribe()

    async def gen():
        try:
            # replay recent history first so a client that connects mid-run
            # (or right after refreshing the page) isn't starting blind
            for e in bus.recent(case_id=case_id, limit=50):
                yield f"data: {json.dumps(e)}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.get_event_loop().run_in_executor(None, q.get, True, 15)
                except Exception:  # noqa: BLE001 — queue.Empty on timeout
                    yield ": keepalive\n\n"
                    continue
                if case_id and event.case_id != case_id:
                    continue
                yield f"data: {json.dumps(event.to_json())}\n\n"
        finally:
            bus.unsubscribe(q)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/events/recent")
def events_recent(case_id: Optional[str] = Query(None), limit: int = Query(50, ge=1, le=200)):
    """Non-streaming fallback: last N pipeline events, polled instead of SSE."""
    return bus.recent(case_id=case_id, limit=limit)


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
    bus.emit(case_id, "evidence_build", "start", "Assembling evidence pack from case data")
    pack = build_evidence_pack(case, reg_store)
    bus.emit(
        case_id, "evidence_build", "ok",
        f"{len(pack.evidence)} evidence items, {len(pack.relationships)} relationships",
        evidence_count=len(pack.evidence), relationship_count=len(pack.relationships),
    )
    audit_log.append("EVIDENCE_ASSEMBLED", case_id, actor="system",
                     detail={"items": len(pack.evidence), "missing": pack.missing_evidence})
    return pack


# ----------------------------------------------------------- investigate ----
@app.post("/investigate/{case_id}", response_model=InvestigationResult)
def run_investigation(case_id: str, body: Optional[Case] = Body(default=None)):
    case = _resolve_case(case_id, body)
    t0 = time.time()

    def emit(stage: str, status: str, detail: str = "", **meta: Any) -> None:
        bus.emit(case_id, stage, status, detail, **meta)

    try:
        result, pack, diag = investigate(case, llm, reg_store, emit=emit)
    except Exception as e:  # noqa: BLE001
        emit("error", "fail", f"{type(e).__name__}: {e}")
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
    notifications: Dict[str, Any] = {}


@app.post("/export/{case_id}", response_model=ExportResponse)
def export_str(case_id: str, draft: STRDraft, actor: str = Query("analyst")):
    if draft.case_id != case_id:
        raise HTTPException(422, "case_id in path and STRDraft body disagree")
    bus.emit(case_id, "export", "start", f"Exporting FIU-IND XML, attested by {actor}")
    xml = build_str_xml(draft, attested_by=actor)
    out_path = config.EXPORT_DIR / f"STR_{case_id}.xml"
    out_path.write_text(xml, encoding="utf-8")
    entry = audit_log.append(
        "STR_ATTESTED_AND_EXPORTED", case_id, actor=actor,
        detail={"gos_tag": draft.gos_tag, "sentences": len(draft.narration),
                "file": str(out_path)},
        evidence_refs=draft.evidence_refs,
    )
    notifications = notify_export(draft, xml, entry, actor)
    email_note = notifications.get("email", {}).get("status", "skipped")
    sms_note = notifications.get("sms", {}).get("status", "skipped")
    bus.emit(
        case_id, "export", "ok",
        f"Audit entry #{entry['seq']} written · email {email_note} · sms {sms_note}",
        seq=entry["seq"],
    )
    return ExportResponse(xml=xml, audit_entry=entry, notifications=notifications)


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
