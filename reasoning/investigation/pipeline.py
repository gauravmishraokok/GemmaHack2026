"""Investigation pipeline — the full pass from Case to InvestigationResult.

    Case
      -> build_evidence_pack        (evidence layer)
      -> validator hard gate        (stop on INSUFFICIENT_EVIDENCE)
      -> evidence-first prompt      (prompt.py)
      -> Gemma, schema-constrained  (serving layer, single pass)
      -> model self-gate            (evidence_sufficiency == INSUFFICIENT stops too)
      -> grounding verification     (amounts / ev_ids vs the actual case)
      -> confidence fusion          (logprobs x grounding -> bands)
      -> STRDraft + InvestigationResult
"""
from __future__ import annotations

from typing import Callable, Dict, Optional, Tuple

from shared_contracts import (
    Case,
    EvidencePack,
    InvestigationResult,
    STRDraft,
)
from serving.llm_client import LLMClient
from serving.schemas import INVESTIGATION_SCHEMA
from evidence.builder import build_evidence_pack
from evidence.regulations import RegulationStore
from evidence.validator import validate
from investigation.prompt import SYSTEM_PROMPT, build_user_prompt
from investigation.confidence import score_narration, overall_confidence
from investigation.grounding import verify_amounts_cited

# (stage, status, detail, **meta) -> None. Kept as a plain callable rather than
# importing api.events directly, so this module stays FastAPI/transport-free
# and testable without a running event bus.
EmitFn = Callable[..., None]


def _noop_emit(*_args, **_kwargs) -> None:
    pass


def investigate(
    case: Case,
    llm: LLMClient,
    reg_store: RegulationStore,
    emit: Optional[EmitFn] = None,
) -> Tuple[InvestigationResult, EvidencePack, Dict]:
    """Returns (result, evidence_pack, diagnostics).

    If `emit` is given, publishes one start/ok(or fail) pair per pipeline stage
    (api.events.STAGES) so a caller (e.g. the SSE endpoint) can drive a live
    stage-by-stage UI off the real pipeline, not a fake timer.
    """
    emit = emit or _noop_emit

    emit("evidence_build", "start", "Assembling evidence pack from case data")
    pack = build_evidence_pack(case, reg_store)
    emit(
        "evidence_build", "ok",
        f"{len(pack.evidence)} evidence items, {len(pack.relationships)} relationships, "
        f"{len(pack.regulations)} regulation citations",
        evidence_count=len(pack.evidence),
        relationship_count=len(pack.relationships),
    )

    emit("evidence_gate", "start", "Checking evidence sufficiency (deterministic hard gate)")
    ok, missing = validate(pack)

    if not ok:
        emit("evidence_gate", "fail", "; ".join(missing), missing=missing)
        # HARD GATE: no STR is ever drafted past this point.
        result = InvestigationResult(
            case_id=case.case_id,
            investigation_summary=(
                "Investigation halted by the evidence validator. The following "
                "critical evidence is missing or unbacked: " + "; ".join(missing)
            ),
            behaviour_pattern="UNDETERMINED — insufficient evidence",
            suggested_questions=[
                "Can additional transaction history be pulled for the involved accounts?",
                "Are there KYC documents or entity linkages not yet ingested for this cluster?",
                "Does the alerting rule that created this case have supporting context to attach?",
            ],
            str_draft=None,
            status="INSUFFICIENT_EVIDENCE",
        )
        emit("complete", "fail", "Halted at evidence gate — no STR drafted")
        return result, pack, {"gate": "validator", "missing": missing}
    emit("evidence_gate", "ok", "Evidence sufficient — proceeding to Gemma")

    emit("gemma_reasoning", "start", f"Running constrained generation ({llm.__class__.__name__})")
    gen = llm.generate_json(SYSTEM_PROMPT, build_user_prompt(pack), INVESTIGATION_SCHEMA)
    out = gen.parsed
    emit(
        "gemma_reasoning", "ok",
        f"{len(gen.tokens)} tokens generated ({len(gen.content_tokens)} in the constrained answer)",
        total_tokens=len(gen.tokens), answer_tokens=len(gen.content_tokens),
    )

    emit("model_gate", "start", "Checking the model's own evidence_sufficiency verdict")
    if out.get("evidence_sufficiency") == "INSUFFICIENT":
        emit("model_gate", "fail", "Model judged its own evidence insufficient")
        # Second gate: the model itself judged the evidence too thin.
        result = InvestigationResult(
            case_id=case.case_id,
            investigation_summary=out.get("investigation_summary", ""),
            behaviour_pattern=out.get("behaviour_pattern", ""),
            suggested_questions=out.get("suggested_questions", []),
            str_draft=None,
            status="INSUFFICIENT_EVIDENCE",
        )
        emit("complete", "fail", "Halted at model self-assessment gate — no STR drafted")
        return result, pack, {"gate": "model_self_assessment", "model": gen.model}
    emit("model_gate", "ok", f"Model verdict: {out.get('evidence_sufficiency', 'SUFFICIENT')}")

    emit("grounding", "start", "Verifying every cited amount and EV-id against the ledger")
    narration = score_narration(out["narration"], gen, case, pack)
    amount_violations = verify_amounts_cited(out.get("amounts_cited", []), case)
    emit(
        "grounding",
        "fail" if amount_violations else "ok",
        f"{len(amount_violations)} unverifiable amount(s)" if amount_violations else "all cited amounts verified",
        violations=amount_violations,
    )

    evidence_refs = sorted(
        {ea["ev_id"] for ea in out.get("evidence_assessment", []) if ea.get("ev_id")}
    )

    str_draft = STRDraft(
        case_id=case.case_id,
        gos_tag=out["gos_tag"],
        narration=narration,
        recommended_action=out["recommended_action"],
        amounts_cited=out.get("amounts_cited", []),
        evidence_refs=evidence_refs,
    )

    result = InvestigationResult(
        case_id=case.case_id,
        investigation_summary=out["investigation_summary"],
        behaviour_pattern=out["behaviour_pattern"],
        suggested_questions=out["suggested_questions"],
        str_draft=str_draft,
        status="OK",
    )

    overall = overall_confidence(narration)
    emit(
        "confidence", "ok",
        f"overall confidence {overall:.0%} across {len(narration)} sentences",
        overall_confidence=overall,
        bands=[n.band for n in narration],
    )

    diagnostics = {
        "model": gen.model,
        "logprobs_available": gen.logprobs_available,
        "total_tokens": len(gen.tokens),
        "answer_tokens": len(gen.content_tokens),
        "overall_confidence": overall,
        "amount_violations": amount_violations,
        "evidence_assessment": out.get("evidence_assessment", []),
        "model_sufficiency": out.get("evidence_sufficiency"),
    }
    emit("complete", "ok", f"STR drafted — {result.str_draft.gos_tag}")
    return result, pack, diagnostics
