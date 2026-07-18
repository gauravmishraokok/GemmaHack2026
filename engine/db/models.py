"""
SQLAlchemy models for the engine database.
Defaults to SQLite (file: engine/data/engine.db) — swap DATABASE_URL for Postgres.
"""

import os
from sqlalchemy import (
    create_engine, Column, String, Float, Integer,
    DateTime, JSON, Text, ForeignKey, Boolean, Index,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///" + os.path.join(os.path.dirname(__file__), "..", "data", "engine.db"),
)

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
Base = declarative_base()


class CaseModel(Base):
    __tablename__ = "cases"

    case_id = Column(String, primary_key=True)
    risk_p = Column(Float, nullable=False)
    risk_margin = Column(Float, nullable=False)
    risk_ood = Column(Float, nullable=False)
    risk_band = Column(String, nullable=False)
    member_alert_ids = Column(JSON, default=list)
    accounts = Column(JSON, default=list)
    shared_pan_groups = Column(JSON, default=list)  # [{"pan": ..., "accounts": [...]}]
    alert_details = Column(JSON, default=list)      # [{"account", "alert_type", "detail"}]

    transactions = relationship("TransactionModel", back_populates="case")
    graph_edges = relationship("GraphEdgeModel", back_populates="case")
    entities = relationship("EntityModel", back_populates="case")


class TransactionModel(Base):
    __tablename__ = "transactions"

    txn_id = Column(String, primary_key=True)
    case_id = Column(String, ForeignKey("cases.case_id"), nullable=False, index=True)
    from_account = Column(String, nullable=False, index=True)
    to_account = Column(String, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="INR")
    timestamp = Column(DateTime, index=True)
    typology_flag = Column(String, nullable=True)
    xgb_score = Column(Float, nullable=True)

    case = relationship("CaseModel", back_populates="transactions")


class GraphEdgeModel(Base):
    __tablename__ = "graph_edges"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String, ForeignKey("cases.case_id"), nullable=False, index=True)
    source = Column(String, nullable=False)
    target = Column(String, nullable=False)
    relation = Column(String, nullable=False)
    weight = Column(Float, nullable=True)

    case = relationship("CaseModel", back_populates="graph_edges")


class EntityModel(Base):
    __tablename__ = "entities"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String, ForeignKey("cases.case_id"), nullable=False, index=True)
    entity_id = Column(String, nullable=False)
    entity_type = Column(String, nullable=False)
    name = Column(String, nullable=True)
    owner_pan = Column(String, nullable=True, index=True)
    director_of = Column(JSON, nullable=True)
    kyc_status = Column(String, nullable=True)      # VERIFIED | PENDING | FAILED
    entity_subtype = Column(String, nullable=True)  # Shell Company | Individual | Registered Business
    jurisdiction = Column(String, nullable=True)    # High Risk | Standard
    linked_company = Column(String, nullable=True)

    case = relationship("CaseModel", back_populates="entities")


class AuditLogModel(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    case_id = Column(String, nullable=False)
    action = Column(String, nullable=False)
    actor = Column(String, nullable=True)
    timestamp = Column(DateTime, nullable=False)
    details = Column(JSON, nullable=True)


class ComparisonMetricModel(Base):
    __tablename__ = "comparison_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model = Column(String, nullable=False)
    precision = Column(Float, nullable=False)
    recall = Column(Float, nullable=False)
    threshold = Column(Float, nullable=False)
    auprc = Column(Float, nullable=True)
    auroc = Column(Float, nullable=True)


def create_tables():
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
