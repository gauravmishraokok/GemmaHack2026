"""
SentinelAI — Shared Contract Models
=====================================
Commit this file FIRST, before Person 1 and Person 2 branch off to build
in parallel. Both services import these models AS-IS. Do not modify a
field name/type without pinging your teammate first — this file is the
entire reason two people can build separately and merge in an afternoon
instead of a day.

Person 1 (engine, port 8001)    PRODUCES: Case, CaseSummary, ComparisonMetric
Person 2 (reasoning, port 8002) PRODUCES: EvidencePack, STRDraft, InvestigationResult
Both consume each other's output types below.
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
    typology_flag: Optional[str] = None  # "structuring" | "layering" | "smurfing" | ...


class GraphEdge(BaseModel):
    source: str
    target: str
    relation: Literal["SENT", "OWNED_BY", "DIRECTOR_OF", "LINKED_PAN"]
    weight: Optional[float] = None


class Entity(BaseModel):
    id: str
    type: Literal["Account", "Person", "Company", "PAN"]
    name: Optional[str] = None
    owner_pan: Optional[str] = None
    director_of: Optional[List[str]] = None


class RiskScore(BaseModel):
    p: float      # probe-predicted probability of risk, 0-1
    margin: float # |p - 0.5| * 2  -> confidence in the decision, 0-1
    ood: float    # mahalanobis distance from training centroid (OOD flag)


class Case(BaseModel):
    case_id: str
    risk: RiskScore
    risk_band: Literal["RED", "YELLOW", "GREEN"]
    member_alert_ids: List[str]
    accounts: List[str]
    transactions: List[Transaction]
    graph_edges: List[GraphEdge]
    entities: List[Entity]


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
