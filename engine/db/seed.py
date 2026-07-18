"""
SentinelAI Engine — Seed pipeline (Phases 1-10).

Flow (see ENGINE_STATUS.md / interface contract):
  1.  Load raw IBM AML transactions (stratified sample optional)
  2.  Synthetic KYC/PAN consolidation (shared PAN per real laundering ring)
  3.  Rule engine  -> flagged accounts, alerts, candidate transactions
  4.  XGBoost refinement -> confirmed suspicious txns (+ drift watchdog,
      warm-start weight adaptation when the data has drifted)
  5.  Transaction-only graph
  6.  Louvain clustering + case assembly (shared_pan_groups, size caps)
  7.  Gemma probe -> (risk_p, margin, ood) per case
  8.  Model evaluation (probe vs xgboost vs rule_count)
  9.  DB persistence (cases, txns, entities, edges, metrics, audit_log)
  10. hero_cases.json — array of contract-valid Case objects for Person 2

Usage:
    python -m engine.db.seed --sample 100000
    python -m engine.db.seed --force            # retrain probe
    USE_GEMMA=0 python -m engine.db.seed        # TF-IDF probe fallback
"""

import os
import sys
import json
import argparse
from datetime import datetime
from typing import Dict, List

# torch MUST be imported before numpy on Windows — numpy loads Intel MKL DLLs
# that conflict with torch's if torch loads second.
try:
    import torch  # noqa: F401
except Exception:
    pass  # torch unavailable; probe falls back to TF-IDF

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from engine.ingestion.load_saml_d import load as load_transactions
from engine.ingestion.synth_identity import consolidate
from engine.rules.engine import run_rules
from engine.graph.build_graph import build_txn_graph
from engine.graph.cluster import detect_communities, communities_to_cases
from engine.risk.probe import GemmaProbe
from engine.risk.baselines import XGBBaseline, XGB_JSON_PATH, XGB_META_PATH
from engine.risk.drift import check_drift
from engine.risk.compare import compute_comparison
from engine.db.models import (
    create_tables, SessionLocal,
    CaseModel, TransactionModel, GraphEdgeModel, EntityModel,
    ComparisonMetricModel, AuditLogModel,
)
from shared_contracts import Case

HERO_CASES_PATH = os.path.join(os.path.dirname(__file__), "..", "fixtures", "hero_cases.json")
DATA_DIR        = os.path.join(os.path.dirname(__file__), "..", "data")

XGB_CONFIRM_THRESHOLD = 0.4
XGB_CONFIRM_FLOOR     = 0.3
MIN_CONFIRMED_TXNS    = 20
# Account-level ML flagging: an account with >= MIN_HIGH_SCORE_TXNS transactions
# scoring >= HIGH_SCORE_CUTOFF is flagged even if no rule fired on it. One high
# score can be noise; repeated high scores on one account are a pattern.
HIGH_SCORE_CUTOFF     = 0.7
MIN_HIGH_SCORE_TXNS   = 2
LABEL_POSITIVE_CUTOFF = 0.05   # continuous case label -> binary for training/eval

RED_CUTOFF    = 0.7
YELLOW_CUTOFF = 0.4


def risk_band(p: float, red: float = RED_CUTOFF, yellow: float = YELLOW_CUTOFF) -> str:
    if p >= red:
        return "RED"
    if p >= yellow:
        return "YELLOW"
    return "GREEN"


def _naive_iso(ts) -> str:
    """ISO-8601 without timezone (contract §4 note)."""
    try:
        t = pd.Timestamp(ts)
        if t.tzinfo is not None:
            t = t.tz_localize(None)
        return t.to_pydatetime().replace(microsecond=0).isoformat()
    except Exception:
        return datetime.now().replace(microsecond=0).isoformat()


def case_to_contract(raw_case: Dict, p: float, margin: float, ood: float) -> Dict:
    """
    Convert an internal raw case into a contract-§4-shaped dict.
    Single source of shape for BOTH the DB write and hero_cases.json.
    """
    case_id = raw_case["case_id"]
    txns_df = raw_case["transactions"]
    kyc     = raw_case.get("kyc", {})
    accounts = raw_case["accounts"]

    # --- Transactions ---
    transactions = []
    for i, (_, row) in enumerate(txns_df.iterrows(), start=1):
        transactions.append({
            "txn_id":        f"{case_id}-{row.get('txn_id', f'TXN-{i:05d}')}",
            "from_account":  str(row["sender_account"]),
            "to_account":    str(row["receiver_account"]),
            "amount":        float(row["amount"]),
            "currency":      str(row.get("payment_currency") or "INR"),
            "timestamp":     _naive_iso(row.get("timestamp")),
            "typology_flag": row.get("typology_flag") if pd.notna(row.get("typology_flag")) else None,
            "xgb_score":     round(float(row["xgb_score"]), 4) if pd.notna(row.get("xgb_score")) else None,
        })

    # --- Entities: one Account entity per account + PAN nodes for shared PANs ---
    entities = []
    for acc in accounts:
        rec = kyc.get(acc) or {}
        entities.append({
            "id":             acc,
            "type":           "Account",
            "name":           f"A/c {acc}",
            "owner_pan":      rec.get("pan"),
            "director_of":    None,
            "kyc_status":     rec.get("kyc_status"),
            "entity_subtype": rec.get("entity_subtype"),
            "jurisdiction":   rec.get("jurisdiction"),
            "linked_company": rec.get("linked_company"),
        })

    shared_pan_groups = raw_case.get("shared_pan_groups", [])
    for grp in shared_pan_groups:
        entities.append({
            "id":   f"PAN-{grp['pan']}",
            "type": "PAN",
            "name": grp["pan"],
            "owner_pan": None, "director_of": None,
            "kyc_status": None, "entity_subtype": None,
            "jurisdiction": None, "linked_company": None,
        })

    # --- Graph edges: SENT aggregated per pair (weight = max xgb_score),
    #     LINKED_PAN account -> PAN node for every shared-PAN account ---
    pair_weight: Dict = {}
    for t in transactions:
        key = (t["from_account"], t["to_account"])
        w = t["xgb_score"] or 0.0
        pair_weight[key] = max(pair_weight.get(key, 0.0), w)

    graph_edges = [
        {"source": s, "target": d, "relation": "SENT", "weight": round(w, 4)}
        for (s, d), w in pair_weight.items()
    ]
    for grp in shared_pan_groups:
        for acc in grp["accounts"]:
            graph_edges.append({
                "source": acc, "target": f"PAN-{grp['pan']}",
                "relation": "LINKED_PAN", "weight": 1.0,
            })

    return {
        "case_id":           case_id,
        "risk":              {"p": round(p, 4), "margin": round(margin, 4), "ood": round(ood, 4)},
        "risk_band":         risk_band(p),
        "member_alert_ids":  raw_case.get("member_alert_ids", []),
        "accounts":          accounts,
        "transactions":      transactions,
        "graph_edges":       graph_edges,
        "entities":          entities,
        "shared_pan_groups": shared_pan_groups,
        "alert_details":     raw_case.get("alert_details", []),
    }


def run_seed(force: bool = False, sample_n: int = None):
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(os.path.dirname(HERO_CASES_PATH), exist_ok=True)
    create_tables()

    # =========================================================================
    print("\n=== Phase 1: Load raw transactions ===")
    df = load_transactions(sample_n=sample_n)

    # =========================================================================
    print("\n=== Phase 2: Synthetic KYC/PAN consolidation ===")
    df, kyc = consolidate(df)

    # =========================================================================
    print("\n=== Phase 3: Rule engine (coarse behavioral filter) ===")
    rule_flagged, alerts_df, txn_typology = run_rules(df)

    # =========================================================================
    print("\n=== Phase 4: XGBoost refinement + drift watchdog ===")
    if os.path.exists(XGB_JSON_PATH) and os.path.exists(XGB_META_PATH):
        xgb = XGBBaseline.load_pretrained()
    elif XGBBaseline.is_trained() and not force:
        print("[xgb] Loading locally trained model.")
        xgb = XGBBaseline.load()
    else:
        print("[xgb] No Kaggle pretrained files — training locally (lower quality fallback).")
        xgb = XGBBaseline()
        xgb.fit_on_transactions(df)
        xgb.save()

    # Scoring is vectorized and cheap — score everything, filter after.
    scores = xgb.score_transactions(df)
    df["xgb_score"] = scores

    # Drift watchdog — read-only vs the Kaggle baseline distribution
    drift_report = check_drift(df, scores, xgb._p75, xgb._p95)
    if drift_report.get("drifted"):
        # Dynamic weight update: warm-start extra boosting rounds on this run's
        # labeled data, then re-score with the adapted ensemble.
        if xgb.adapt(df):
            scores = xgb.score_transactions(df)
            df["xgb_score"] = scores
            drift_report["adapted"] = True

    # Account-level ML flagging: accounts with repeated high-score transactions
    # are suspicious even when no rule fired on them.
    hi = df[df["xgb_score"] >= HIGH_SCORE_CUTOFF]
    acc_hits = pd.concat([hi["sender_account"], hi["receiver_account"]]).value_counts()
    ml_flagged = set(acc_hits[acc_hits >= MIN_HIGH_SCORE_TXNS].index)
    flagged_accounts = rule_flagged | ml_flagged
    print(f"[xgb] Flagged accounts: {len(rule_flagged)} by rules + "
          f"{len(ml_flagged - rule_flagged)} extra by repeated high scores "
          f"= {len(flagged_accounts)} total.")

    touching = (
        df["sender_account"].isin(flagged_accounts)
        | df["receiver_account"].isin(flagged_accounts)
    )
    thresh = XGB_CONFIRM_THRESHOLD
    confirmed = df[touching & (df["xgb_score"] >= thresh)]
    if len(confirmed) < MIN_CONFIRMED_TXNS:
        print(f"[xgb] Only {len(confirmed)} txns >= {thresh} — lowering threshold to {XGB_CONFIRM_FLOOR}.")
        thresh = XGB_CONFIRM_FLOOR
        confirmed = df[touching & (df["xgb_score"] >= thresh)]
    if len(confirmed) < MIN_CONFIRMED_TXNS:
        # Last resort so a small/clean sample still demos: take the top-scoring txns
        top_n = min(max(MIN_CONFIRMED_TXNS * 5, 100), len(df))
        print(f"[xgb] Still only {len(confirmed)} — falling back to top {top_n} by score.")
        confirmed = df.nlargest(top_n, "xgb_score")
    confirmed = confirmed.copy()
    confirmed["typology_flag"] = confirmed["txn_id"].map(txn_typology)
    print(f"[xgb] {len(confirmed):,} confirmed suspicious transactions (threshold {thresh}).")

    # =========================================================================
    print("\n=== Phase 5: Transaction-only graph ===")
    G = build_txn_graph(confirmed)
    print(f"  {G.number_of_nodes()} account nodes, {G.number_of_edges()} edges.")

    # =========================================================================
    print("\n=== Phase 6: Louvain clustering + case assembly ===")
    communities = detect_communities(G)
    raw_cases = communities_to_cases(communities, confirmed, alerts_df, kyc)
    print(f"  {len(communities)} communities -> {len(raw_cases)} cases.")
    if not raw_cases:
        print("[seed] ERROR: no cases assembled. Increase --sample or check thresholds.")
        return []

    labels_cont = [c["label"] for c in raw_cases]
    labels_bin = [int(l > LABEL_POSITIVE_CUTOFF) for l in labels_cont]
    print(f"  Case labels: {sum(labels_bin)} positive / {len(labels_bin) - sum(labels_bin)} negative "
          f"(cutoff {LABEL_POSITIVE_CUTOFF} on laundering value fraction).")

    # =========================================================================
    print("\n=== Phase 7: Gemma probe risk scoring ===")
    if GemmaProbe.is_trained() and not force:
        print("[probe] Loading saved probe.")
        probe = GemmaProbe.load()
    else:
        probe = GemmaProbe()
        probe.fit_with_split(raw_cases, labels_bin, test_size=0.2, val_size=0.1)
        probe.save()

    # =========================================================================
    print("\n=== Phase 8: Model evaluation ===")
    comparison_data = compute_comparison(probe, xgb, raw_cases, labels_bin, test_size=0.2)

    # =========================================================================
    print("\n=== Phase 9: DB persistence ===")
    db = SessionLocal()
    db.query(ComparisonMetricModel).delete()
    db.query(EntityModel).delete()
    db.query(GraphEdgeModel).delete()
    db.query(TransactionModel).delete()
    db.query(CaseModel).delete()
    db.commit()

    contract_cases: List[Dict] = []
    for raw_case in raw_cases:
        try:
            p, margin, ood = probe.predict(raw_case)
        except Exception as e:
            print(f"  [warn] Probe predict failed for {raw_case['case_id']}: {e}")
            p, margin, ood = 0.5, 0.0, 0.0

        cc = case_to_contract(raw_case, p, margin, ood)
        contract_cases.append(cc)

        db.add(CaseModel(
            case_id=cc["case_id"],
            risk_p=cc["risk"]["p"], risk_margin=cc["risk"]["margin"], risk_ood=cc["risk"]["ood"],
            risk_band=cc["risk_band"],
            member_alert_ids=cc["member_alert_ids"],
            accounts=cc["accounts"],
            shared_pan_groups=cc["shared_pan_groups"],
            alert_details=cc["alert_details"],
        ))
        for t in cc["transactions"]:
            db.add(TransactionModel(
                txn_id=t["txn_id"], case_id=cc["case_id"],
                from_account=t["from_account"], to_account=t["to_account"],
                amount=t["amount"], currency=t["currency"],
                timestamp=datetime.fromisoformat(t["timestamp"]),
                typology_flag=t["typology_flag"], xgb_score=t["xgb_score"],
            ))
        for e in cc["graph_edges"]:
            db.add(GraphEdgeModel(
                case_id=cc["case_id"], source=e["source"], target=e["target"],
                relation=e["relation"], weight=e["weight"],
            ))
        for ent in cc["entities"]:
            db.add(EntityModel(
                case_id=cc["case_id"], entity_id=ent["id"], entity_type=ent["type"],
                name=ent["name"], owner_pan=ent["owner_pan"], director_of=ent["director_of"],
                kyc_status=ent["kyc_status"], entity_subtype=ent["entity_subtype"],
                jurisdiction=ent["jurisdiction"], linked_company=ent["linked_company"],
            ))
        db.add(AuditLogModel(
            case_id=cc["case_id"], action="SEED", actor="seed_pipeline",
            timestamp=datetime.now(),
            details={"risk_p": cc["risk"]["p"], "band": cc["risk_band"],
                     "n_txns": len(cc["transactions"])},
        ))

    for cm in comparison_data:
        db.add(ComparisonMetricModel(
            model=cm["model"], precision=cm["precision"], recall=cm["recall"],
            threshold=cm["threshold"], auprc=cm.get("auprc"), auroc=cm.get("auroc"),
        ))

    db.add(AuditLogModel(
        case_id="*", action="SEED", actor="seed_pipeline", timestamp=datetime.now(),
        details={"n_cases": len(contract_cases), "sample_n": sample_n,
                 "drift": drift_report, "xgb_threshold": thresh},
    ))
    db.commit()
    db.close()
    print(f"  Saved {len(contract_cases)} cases + audit log entries.")

    # =========================================================================
    print("\n=== Phase 10: hero_cases.json (Person 2 fixtures) ===")
    # Rank REDs by evidence richness first (shared PANs, alerts), then risk —
    # Person 2's evidence validator hard-gates on having >=1 relationship, so
    # hero cases must carry citable identity/alert evidence, not just a score.
    def _evidence_rank(c):
        return (
            min(len(c["shared_pan_groups"]), 2),
            min(len(c["alert_details"]), 3),
            c["risk"]["p"],
        )

    ranked = sorted(contract_cases, key=lambda c: c["risk"]["p"], reverse=True)
    reds   = sorted(
        [c for c in ranked if c["risk_band"] == "RED"],
        key=_evidence_rank, reverse=True,
    )
    greens = [c for c in ranked if c["risk_band"] == "GREEN"]
    yels   = [c for c in ranked if c["risk_band"] == "YELLOW"]
    hero = reds[:4] + (greens or yels)[:1]
    if len(hero) < 5:
        hero = ranked[:5]

    # Contract gate: every hero case must validate before we ship the fixture
    for c in hero:
        Case.model_validate(c)

    with open(HERO_CASES_PATH, "w", encoding="utf-8") as f:
        json.dump(hero, f, indent=2, default=str)
    print(f"  Wrote {len(hero)} contract-validated hero cases -> {HERO_CASES_PATH}")

    print("\n=== Model evaluation summary ===")
    if probe.eval_report:
        print(f"  Probe:   {probe.eval_report}")
    if xgb.eval_report:
        print(f"  XGBoost: {xgb.eval_report}")
    for cm in comparison_data:
        print(f"  {cm['model']:12s} P={cm['precision']:.4f} R={cm['recall']:.4f} "
              f"AUPRC={cm.get('auprc', 'n/a')}")

    print("\n=== Seed complete. ===")
    return contract_cases


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--force",  action="store_true", help="Force re-train the probe")
    parser.add_argument("--sample", type=int, default=None,
                        help="Stratified sample N rows from the CSV (default: all)")
    args = parser.parse_args()
    run_seed(force=args.force, sample_n=args.sample)
