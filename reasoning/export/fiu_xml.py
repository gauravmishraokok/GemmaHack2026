"""FIU-IND STR XML export.

Template-fills an STR skeleton from the STRDraft. Structure follows the
spirit of FIU-IND's electronic STR format (report header, ground of
suspicion, narration, transaction references); the exact production XSD is
not public, so this is a faithful demo skeleton, verified well-formed by an
ElementTree round-trip before it leaves the service.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from xml.dom import minidom

from shared_contracts import STRDraft

REPORTING_ENTITY = {
    "name": "Demo Cooperative Bank Ltd (viGEMMAlya)",
    "fiu_re_id": "REDEMO0001",
    "category": "Cooperative Bank",
    "principal_officer": "Principal Officer (attesting analyst)",
}


def build_str_xml(draft: STRDraft, attested_by: str = "analyst") -> str:
    root = ET.Element("STRBatch", version="1.0", generator="viGEMMAlya-reasoning")

    header = ET.SubElement(root, "ReportHeader")
    ET.SubElement(header, "ReportType").text = "STR"
    ET.SubElement(header, "ReportDate").text = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    re_el = ET.SubElement(header, "ReportingEntity")
    ET.SubElement(re_el, "Name").text = REPORTING_ENTITY["name"]
    ET.SubElement(re_el, "FIUREId").text = REPORTING_ENTITY["fiu_re_id"]
    ET.SubElement(re_el, "Category").text = REPORTING_ENTITY["category"]
    ET.SubElement(re_el, "PrincipalOfficer").text = REPORTING_ENTITY["principal_officer"]

    report = ET.SubElement(root, "SuspicionReport", caseRef=draft.case_id)
    ET.SubElement(report, "GroundOfSuspicion", code=draft.gos_tag)

    narration_el = ET.SubElement(report, "Narration")
    for i, sent in enumerate(draft.narration, 1):
        s = ET.SubElement(
            narration_el,
            "Sentence",
            seq=str(i),
            confidence=f"{sent.confidence:.3f}",
            band=sent.band,
        )
        s.text = sent.sentence

    amounts_el = ET.SubElement(report, "AmountsCited", currency="INR")
    for a in draft.amounts_cited:
        ET.SubElement(amounts_el, "Amount").text = f"{a:.2f}"

    ev_el = ET.SubElement(report, "EvidenceReferences")
    for ref in draft.evidence_refs:
        ET.SubElement(ev_el, "EvidenceRef").text = ref

    ET.SubElement(report, "RecommendedAction").text = draft.recommended_action

    attest = ET.SubElement(report, "Attestation")
    ET.SubElement(attest, "AttestedBy").text = attested_by
    ET.SubElement(attest, "AttestedAt").text = datetime.now(timezone.utc).isoformat()
    ET.SubElement(attest, "Statement").text = (
        "This report was drafted by viGEMMAlya under schema-constrained decoding "
        "and verified sentence-by-sentence by the attesting officer."
    )

    raw = ET.tostring(root, encoding="unicode")
    ET.fromstring(raw)  # round-trip: guarantee well-formedness before export
    pretty = minidom.parseString(raw).toprettyxml(indent="  ")
    return pretty
