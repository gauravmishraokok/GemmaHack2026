"""
Thin re-export of the root shared_contracts.py — the single source of truth.
Kept so `from engine.shared_contracts import ...` keeps working.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared_contracts import *          # noqa: F401,F403
from shared_contracts import (           # noqa: F401 — explicit for IDEs
    Transaction, GraphEdge, Entity, RiskScore, SharedPanGroup, AlertDetail,
    Case, CaseSummary, ComparisonMetric,
    EvidenceItem, TimelineEvent, Relationship, RegulationRef, EvidencePack,
    NarrationSentence, STRDraft, InvestigationResult,
)
