"""
SentinelAI — Shared Contract Models
=====================================
Single source of truth for the Person 1 (engine :8001) → Person 2
(reasoning :8002) interface. Matches the INTERFACE CONTRACT doc §3 exactly.
Both services import these models AS-IS. Do not modify a field name/type
without pinging your teammate first.

Person 1 (engine, port 8001)    PRODUCES: Case, CaseSummary, ComparisonMetric
Person 2 (reasoning, port 8002) PRODUCES: EvidencePack, STRDraft, InvestigationResult
"""

from pydantic import BaseModel
from typing import List, Optional, Literal
from datetime import datetime


# ============================================================
# Person 1 -> Person 2 / Frontend
# ============================================================

class Transaction(BaseModel):
    txn_id: str
    from_account: str
    to_account: str
    amount: float
    currency: str = "INR"
    timestamp: datetime
    typology_flag: Optional[str] = None  # "structuring"|"layering"|"smurfing"|"round_tripping"|"funnel"|None (lowercase)
    xgb_score: Optional[float] = None    # per-txn ML anomaly score 0..1 (Phase 4); None if unavailable — never fabricated


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: Literal["SENT", "OWNED_BY", "DIRECTOR_OF", "LINKED_PAN"]
    weight: Optional[float] = None


class Entity(BaseModel):
    id: str
    type: Literal["Account", "Person", "Company", "PAN"]  # closed enum — shell-ness rides on entity_subtype/kyc_status
    name: Optional[str] = None
    owner_pan: Optional[str] = None      # required on Account entities in a ring
    director_of: Optional[List[str]] = None
    kyc_status: Optional[Literal["VERIFIED", "PENDING", "FAILED"]] = None
    entity_subtype: Optional[str] = None  # "Shell Company" | "Individual" | "Registered Business"
    jurisdiction: Optional[str] = None    # "High Risk" | "Standard" | ...
    linked_company: Optional[str] = None


class RiskScore(BaseModel):
    p: float      # probe-predicted probability of risk, 0-1
    margin: float # |p - 0.5| * 2  -> confidence in the decision, 0-1
    ood: float    # mahalanobis distance from training centroid (OOD flag)


class SharedPanGroup(BaseModel):
    pan: str
    accounts: List[str]  # >=2 account ids controlled by one PAN


class AlertDetail(BaseModel):
    account: str
    alert_type: Literal["velocity", "threshold", "structuring"]
    detail: str  # human-readable, e.g. "6 txns in 48h totalling $59.2k"


class Case(BaseModel):
    case_id: str
    risk: RiskScore
    risk_band: Literal["RED", "YELLOW", "GREEN"]
    member_alert_ids: List[str]
    accounts: List[str]
    transactions: List[Transaction]
    graph_edges: List[GraphEdge]
    entities: List[Entity]
    shared_pan_groups: List[SharedPanGroup] = []
    alert_details: List[AlertDetail] = []


class CaseSummary(BaseModel):
    case_id: str
    risk_band: Literal["RED", "YELLOW", "GREEN"]
    p: float
    member_count: int


class ComparisonMetric(BaseModel):
    model: Literal["gemma_probe", "xgboost", "rule_count"]
    precision: float
    recall: float
    threshold: float


# ============================================================
# Person 2 internal -> Frontend
# ============================================================

class EvidenceItem(BaseModel):
    ev_id: str
    kind: str
    source_ref: str
    value: str


class TimelineEvent(BaseModel):
    ts: datetime
    event: str


class Relationship(BaseModel):
    type: str  # "shared_director" | "linked_pan" | "repeat_beneficiary" | ...
    entities: List[str]


class RegulationRef(BaseModel):
    section: str
    text_snippet: str
    relevance: str


class EvidencePack(BaseModel):
    case_id: str
    evidence: List[EvidenceItem]
    timeline: List[TimelineEvent]
    relationships: List[Relationship]
    regulations: List[RegulationRef]
    risk: RiskScore
    missing_evidence: List[str] = []


class NarrationSentence(BaseModel):
    sentence: str
    confidence: float
    band: Literal["green", "yellow", "red"]


class STRDraft(BaseModel):
    case_id: str
    gos_tag: str
    narration: List[NarrationSentence]
    recommended_action: str
    amounts_cited: List[float]
    evidence_refs: List[str]


class InvestigationResult(BaseModel):
    case_id: str
    investigation_summary: str
    behaviour_pattern: str
    suggested_questions: List[str]
    str_draft: Optional[STRDraft] = None
    status: Literal["OK", "INSUFFICIENT_EVIDENCE"]
