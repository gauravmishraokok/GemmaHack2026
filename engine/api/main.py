"""
SentinelAI Engine API — Port 8001 (serve mode).
Run: uvicorn engine.api.main:app --port 8001 --reload

Serves the interface contract exactly: Case / CaseSummary / ComparisonMetric,
including the §3 extensions (xgb_score, KYC entity fields, shared_pan_groups,
alert_details).
"""

import os
import sys
from typing import List, Optional
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import joinedload

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.db.models import (
    get_db, SessionLocal, CaseModel, TransactionModel,
    GraphEdgeModel, EntityModel, ComparisonMetricModel, AuditLogModel,
)
from shared_contracts import (
    Case, CaseSummary, ComparisonMetric, Transaction, GraphEdge, Entity,
    RiskScore, SharedPanGroup, AlertDetail,
)

app = FastAPI(title="SentinelAI Engine", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # lock to Person 2's origin before any non-local demo
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

VALID_RELATIONS = {"SENT", "OWNED_BY", "DIRECTOR_OF", "LINKED_PAN"}
VALID_ENTITY_TYPES = {"Account", "Person", "Company", "PAN"}

RED_CUTOFF = 0.7
YELLOW_GAP = 0.3   # §7: yellow cutoff = red cutoff - 0.3


def _band(p: float, red: float = RED_CUTOFF) -> str:
    yellow = max(0.05, red - YELLOW_GAP)
    if p >= red:
        return "RED"
    if p >= yellow:
        return "YELLOW"
    return "GREEN"


def _db_case_to_contract(db_case: CaseModel) -> Case:
    """Convert a fully-loaded CaseModel (relationships eager-loaded) to a Case."""
    transactions = [
        Transaction(
            txn_id=t.txn_id,
            from_account=t.from_account,
            to_account=t.to_account,
            amount=t.amount,
            currency=t.currency or "INR",
            timestamp=t.timestamp or datetime.now(),
            typology_flag=t.typology_flag,
            xgb_score=t.xgb_score,
        )
        for t in db_case.transactions
    ]

    graph_edges = [
        GraphEdge(source=e.source, target=e.target, relation=e.relation, weight=e.weight)
        for e in db_case.graph_edges
        if e.relation in VALID_RELATIONS
    ]

    entities = [
        Entity(
            id=e.entity_id,
            type=e.entity_type if e.entity_type in VALID_ENTITY_TYPES else "Account",
            name=e.name,
            owner_pan=e.owner_pan,
            director_of=e.director_of,
            kyc_status=e.kyc_status,
            entity_subtype=e.entity_subtype,
            jurisdiction=e.jurisdiction,
            linked_company=e.linked_company,
        )
        for e in db_case.entities
    ]

    return Case(
        case_id=db_case.case_id,
        risk=RiskScore(p=db_case.risk_p, margin=db_case.risk_margin, ood=db_case.risk_ood),
        risk_band=db_case.risk_band,
        member_alert_ids=db_case.member_alert_ids or [],
        accounts=db_case.accounts or [],
        transactions=transactions,
        graph_edges=graph_edges,
        entities=entities,
        shared_pan_groups=[SharedPanGroup(**g) for g in (db_case.shared_pan_groups or [])],
        alert_details=[AlertDetail(**a) for a in (db_case.alert_details or [])],
    )


def _load_case_eager(case_id: str, db):
    return (
        db.query(CaseModel)
        .options(
            joinedload(CaseModel.transactions),
            joinedload(CaseModel.graph_edges),
            joinedload(CaseModel.entities),
        )
        .filter(CaseModel.case_id == case_id)
        .first()
    )


# ---- Endpoints ---------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/cases", response_model=List[CaseSummary])
def list_cases(
    risk_band: Optional[str] = Query(None),
    limit: int = Query(50, le=500),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),
):
    q = db.query(CaseModel)
    if risk_band:
        q = q.filter(CaseModel.risk_band == risk_band.upper())
    rows = q.order_by(CaseModel.risk_p.desc()).offset(offset).limit(limit).all()

    if not rows and offset == 0:
        raise HTTPException(
            status_code=503,
            detail="No cases in database. Run: python -m engine.db.seed"
        )

    return [
        CaseSummary(
            case_id=r.case_id,
            risk_band=r.risk_band,
            p=r.risk_p,
            member_count=len(r.member_alert_ids or []),
        )
        for r in rows
    ]


@app.get("/cases/{case_id}", response_model=Case)
def get_case(case_id: str, db=Depends(get_db)):
    row = _load_case_eager(case_id, db)
    if not row:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    return _db_case_to_contract(row)


@app.get("/cases/{case_id}/graph")
def get_case_graph(case_id: str, db=Depends(get_db)):
    """Same data shaped for graph rendering (Person 2 builds its own; kept as extra)."""
    row = _load_case_eager(case_id, db)
    if not row:
        raise HTTPException(status_code=404, detail=f"Case {case_id} not found")
    case = _db_case_to_contract(row)
    return {
        "entities": [e.model_dump() for e in case.entities],
        "edges":    [e.model_dump() for e in case.graph_edges],
    }


class ThresholdRequest(BaseModel):
    threshold: float = 0.6


@app.post("/risk/threshold")
def recompute_bands(body: ThresholdRequest, db=Depends(get_db)):
    """§7: threshold = RED cutoff; YELLOW = threshold - 0.3; else GREEN."""
    rows = db.query(CaseModel).all()
    if not rows:
        raise HTTPException(status_code=503, detail="No cases in database.")

    counts = {"red": 0, "yellow": 0, "green": 0}
    for r in rows:
        band = _band(r.risk_p, body.threshold)
        r.risk_band = band
        counts[band.lower()] += 1

    db.add(AuditLogModel(
        case_id="*", action="THRESHOLD_CHANGE", actor="api",
        timestamp=datetime.now(),
        details={"threshold": body.threshold, "counts": counts},
    ))
    db.commit()
    return counts


@app.get("/metrics/comparison", response_model=List[ComparisonMetric])
def get_comparison_metrics(db=Depends(get_db)):
    rows = db.query(ComparisonMetricModel).all()
    if not rows:
        raise HTTPException(
            status_code=503,
            detail="No comparison metrics. Run: python -m engine.db.seed"
        )
    return [
        ComparisonMetric(
            model=r.model, precision=r.precision, recall=r.recall, threshold=r.threshold,
        )
        for r in rows
    ]


@app.get("/metrics/comparison/full")
def get_comparison_metrics_full(db=Depends(get_db)):
    """Extended: adds auprc/auroc. The base endpoint keeps the frozen shape."""
    rows = db.query(ComparisonMetricModel).all()
    if not rows:
        raise HTTPException(status_code=503, detail="No comparison metrics.")
    return [
        {
            "model":     r.model,
            "precision": r.precision,
            "recall":    r.recall,
            "threshold": r.threshold,
            "auprc":     r.auprc,
            "auroc":     r.auroc,
        }
        for r in rows
    ]


# ---- Startup: seed if empty --------------------------------------------------

@app.on_event("startup")
def startup_event():
    from engine.db.models import create_tables
    create_tables()
    db = SessionLocal()
    count = db.query(CaseModel).count()
    db.close()
    if count == 0:
        print("[startup] DB empty — running seed pipeline...")
        try:
            from engine.db.seed import run_seed
            run_seed()
        except Exception as e:
            print(f"[startup] Seed failed: {e}. Start the server after seeding manually.")
