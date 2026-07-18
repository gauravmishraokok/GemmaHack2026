"""Assembles the EvidencePack a Case is investigated against.

Every EvidenceItem carries a stable ev_id (EV-001, EV-002, ...) and a
source_ref pointing at the raw artifact (txn id, graph edge, document id,
regulation section). The LLM is only ever shown these items, and the
grounding verifier later checks its claims back against them.
"""
from __future__ import annotations

from typing import List

from shared_contracts import Case, EvidenceItem, EvidencePack
from evidence.timeline import build_timeline, format_amount
from evidence.relationships import extract_relationships
from evidence.documents import documents_for_accounts
from evidence.regulations import RegulationStore
from evidence.validator import validate


def _regulation_query(case: Case, relationship_types: List[str]) -> str:
    flags = {t.typology_flag for t in case.transactions if t.typology_flag}
    parts = list(flags) + relationship_types
    if not parts:
        parts = ["suspicious transaction pattern"]
    return "suspicious transactions involving " + ", ".join(sorted(set(parts)))


def build_evidence_pack(case: Case, reg_store: RegulationStore) -> EvidencePack:
    evidence: List[EvidenceItem] = []
    counter = 0

    def add(kind: str, source_ref: str, value: str) -> None:
        nonlocal counter
        counter += 1
        evidence.append(
            EvidenceItem(ev_id=f"EV-{counter:03d}", kind=kind, source_ref=source_ref, value=value)
        )

    # 1. transactions
    for t in sorted(case.transactions, key=lambda x: x.timestamp):
        flag = f", flagged {t.typology_flag}" if t.typology_flag else ""
        xgb = f", XGBoost anomaly score {t.xgb_score:.2f}" if t.xgb_score is not None else ""
        # exact figure, never truncated — the model copies this verbatim and the
        # grounding verifier checks it back against the ledger
        exact = f"{t.amount:.2f}".rstrip("0").rstrip(".")
        add(
            "transaction",
            t.txn_id,
            f"{t.from_account} -> {t.to_account} {format_amount(t.amount, t.currency)} "
            f"(exact: {exact} {t.currency}) on {t.timestamp.isoformat()}{flag}{xgb}",
        )

    # 2. relationships
    relationships = extract_relationships(case)
    for i, r in enumerate(relationships):
        add(
            "relationship",
            f"graph:{r.type}:{i}",
            f"{r.type.replace('_', ' ')}: {' , '.join(r.entities)}",
        )

    # 2b. rule alerts from the engine (velocity / threshold / structuring)
    for i, a in enumerate(case.alert_details):
        add("rule_alert", f"alert:{a.alert_type}:{a.account}", f"{a.alert_type} rule on {a.account}: {a.detail}")

    # 2c. KYC risk indicators — FAILED KYC / shell entities are directly citable.
    # Grouped by identical indicator set: real engine cases can carry 30+ ring
    # accounts with the same flags, and one aggregate line ("12 accounts share
    # FAILED KYC + shell company X") is both cheaper in tokens and stronger
    # evidence than 30 repeats.
    kyc_groups: dict = {}
    for ent in case.entities:
        indicators = []
        if ent.kyc_status and ent.kyc_status != "VERIFIED":
            indicators.append(f"KYC {ent.kyc_status}")
        if ent.entity_subtype and "shell" in ent.entity_subtype.lower():
            indicators.append(ent.entity_subtype)
        if ent.jurisdiction and ent.jurisdiction != "Standard":
            indicators.append(f"{ent.jurisdiction} jurisdiction")
        if indicators:
            key = (", ".join(indicators), ent.linked_company or "")
            kyc_groups.setdefault(key, []).append(ent.id)
    for (indicators, company), ids in kyc_groups.items():
        company_note = f", all linked to {company}" if company else ""
        if len(ids) == 1:
            add("kyc_flag", f"kyc:{ids[0]}", f"{ids[0]}: {indicators}{company_note}")
        else:
            shown = ", ".join(ids[:8]) + (f" (+{len(ids) - 8} more)" if len(ids) > 8 else "")
            add(
                "kyc_flag",
                f"kyc:{'|'.join(ids)}",
                f"{len(ids)} accounts share the same risk profile — {indicators}{company_note}: {shown}",
            )

    # 3. documents (stubbed vision extraction)
    for d in documents_for_accounts(case.accounts):
        add(
            "document",
            d["doc_id"],
            f"{d['doc_type']} for {d['account']} — {d['field']}: {d['value']}",
        )

    # 4. risk score from Person 1's activation probe
    add(
        "risk_score",
        f"probe:{case.case_id}",
        f"Gemma activation-probe risk p={case.risk.p:.2f}, margin={case.risk.margin:.2f}, "
        f"ood={case.risk.ood:.2f}, band={case.risk_band}",
    )

    # 5. regulations (only for cases with actual signal — a thin case gets none,
    # which is exactly what trips the validator's citation slot)
    rel_types = [r.type for r in relationships]
    regulations = []
    if len(case.transactions) >= 3 or relationships:
        regulations = reg_store.search(_regulation_query(case, rel_types), k=3)
        for reg in regulations:
            add("regulation", reg.section, f"{reg.section}: {reg.text_snippet[:180]}...")

    pack = EvidencePack(
        case_id=case.case_id,
        evidence=evidence,
        timeline=build_timeline(case),
        relationships=relationships,
        regulations=regulations,
        risk=case.risk,
        missing_evidence=[],
    )
    ok, missing = validate(pack)
    pack.missing_evidence = missing
    return pack
