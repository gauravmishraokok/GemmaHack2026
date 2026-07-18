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

from typing import Dict, Optional, Tuple

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


def investigate(
    case: Case, llm: LLMClient, reg_store: RegulationStore
) -> Tuple[InvestigationResult, EvidencePack, Dict]:
    """Returns (result, evidence_pack, diagnostics)."""
    pack = build_evidence_pack(case, reg_store)
    ok, missing = validate(pack)

    if not ok:
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
        return result, pack, {"gate": "validator", "missing": missing}

    gen = llm.generate_json(SYSTEM_PROMPT, build_user_prompt(pack), INVESTIGATION_SCHEMA)
    out = gen.parsed

    if out.get("evidence_sufficiency") == "INSUFFICIENT":
        # Second gate: the model itself judged the evidence too thin.
        result = InvestigationResult(
            case_id=case.case_id,
            investigation_summary=out.get("investigation_summary", ""),
            behaviour_pattern=out.get("behaviour_pattern", ""),
            suggested_questions=out.get("suggested_questions", []),
            str_draft=None,
            status="INSUFFICIENT_EVIDENCE",
        )
        return result, pack, {"gate": "model_self_assessment", "model": gen.model}

    narration = score_narration(out["narration"], gen, case, pack)
    amount_violations = verify_amounts_cited(out.get("amounts_cited", []), case)

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

    diagnostics = {
        "model": gen.model,
        "logprobs_available": gen.logprobs_available,
        "total_tokens": len(gen.tokens),
        "answer_tokens": len(gen.content_tokens),
        "overall_confidence": overall_confidence(narration),
        "amount_violations": amount_violations,
        "evidence_assessment": out.get("evidence_assessment", []),
        "model_sufficiency": out.get("evidence_sufficiency"),
    }
    return result, pack, diagnostics
