"""
Baseline risk models — transaction-level XGBoost.

Training approach:
  - XGBoost is trained on INDIVIDUAL TRANSACTIONS with the is_laundering label.
  - With 100k real transactions, this gives ~1k-5k positive samples — enough to
    train a meaningful model with proper stratified CV.
  - Case-level score is then derived by aggregating per-transaction predictions:
      case_risk = max(txn_proba) * 0.6 + mean(txn_proba) * 0.3 + frac_high_risk * 0.1
  - This matches how production AML systems work: score transactions first,
    then roll up to cases.

Rule-count baseline:
  - Normalised alert count per case, zero parameters.
"""

import os
import pickle
import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Tuple

from sklearn.metrics import (
    precision_recall_curve, average_precision_score,
    roc_auc_score, classification_report,
)
from sklearn.model_selection import train_test_split, StratifiedKFold
from sklearn.preprocessing import LabelEncoder

MODELS_DIR       = os.path.join(os.path.dirname(__file__), "..", "data")
XGB_PATH         = os.path.join(MODELS_DIR, "xgb_model.pkl")          # local training output
XGB_JSON_PATH    = os.path.join(MODELS_DIR, "xgb_pretrained.json")    # Kaggle export (native XGB)
XGB_META_PATH    = os.path.join(MODELS_DIR, "xgb_pretrained_meta.json")  # Kaggle export metadata
XGB_ADAPTED_PATH = os.path.join(MODELS_DIR, "xgb_adapted.json")       # drift-adapted (warm-started) model

# Payment type → integer for XGBoost
# IBM AML dataset uses full format names; synthetic data uses ISO-style codes.
# Both map to the same integers so training/inference stay consistent.
_PAYMENT_TYPE_MAP = {
    # IBM AML format names (dominant in real data)
    "Reinvestment": 0, "Wire": 1, "Cheque": 2, "Credit Card": 3,
    "Cash": 4, "ACH": 5, "Bitcoin": 6,
    # Synthetic / SWIFT naming
    "SWIFT": 1, "NEFT": 7, "RTGS": 8, "IMPS": 9,
    # Misc
    "Debit card": 3, "Credit card": 3, "Cash Deposit": 4,
}

# Currency → integer. IBM AML uses full names; synthetic uses ISO codes.
# Both natural-case AND uppercase variants are included because _txn_features
# calls .upper() on currency strings for normalization.
_CURRENCY_MAP = {
    # IBM AML full names (natural case)
    "US Dollar": 0, "Euro": 1, "UK Pound": 2, "Yuan": 3,
    "Bitcoin": 4, "Yen": 5, "Canadian Dollar": 6, "Rupee": 7,
    "Mexican Peso": 8, "Australian Dollar": 9, "Ruble": 10,
    # IBM AML full names (uppercased — what .upper() produces)
    "US DOLLAR": 0, "EURO": 1, "UK POUND": 2, "YUAN": 3,
    "BITCOIN": 4, "YEN": 5, "CANADIAN DOLLAR": 6, "RUPEE": 7,
    "MEXICAN PESO": 8, "AUSTRALIAN DOLLAR": 9, "RUBLE": 10,
    # ISO codes (always uppercase)
    "USD": 0, "EUR": 1, "GBP": 2, "CNY": 3, "JPY": 5,
    "CAD": 6, "INR": 7, "MXN": 8, "AUD": 9, "AED": 11, "SGD": 12,
}


# ── Transaction-level features ────────────────────────────────────────────────

def _txn_features(row: pd.Series, global_amount_p75: float, global_amount_p95: float) -> np.ndarray:
    """
    Extract features from a single transaction row.
    All features are numeric — no encoding needed by XGBoost, but we still
    make currencies and payment types ordinal ints for clarity.
    """
    amount = float(row.get("amount", 0) or 0)
    ts = row.get("timestamp")
    try:
        hour = pd.Timestamp(ts).hour if ts is not None else 12
    except Exception:
        hour = 12

    pay_curr = str(row.get("payment_currency", "INR") or "INR").strip().upper()
    rcv_curr = str(row.get("received_currency", "INR") or "INR").strip().upper()
    pay_type = str(row.get("payment_type", "NEFT") or "NEFT").strip()
    src_bank = str(row.get("sender_bank", "") or "")
    dst_bank = str(row.get("receiver_bank", "") or "")

    return np.array([
        np.log1p(amount),
        hour,
        int(hour < 6),                                          # night transaction
        int(hour >= 22 or hour < 6),                            # unsocial hours
        int(pay_curr != rcv_curr),                              # currency mismatch
        _CURRENCY_MAP.get(pay_curr, 6),                         # payment currency id
        _CURRENCY_MAP.get(rcv_curr, 6),                         # receiving currency id
        _PAYMENT_TYPE_MAP.get(pay_type, 8),                     # payment method id
        int(src_bank != dst_bank and src_bank and dst_bank),    # cross-institution
        int(pay_type in ("SWIFT", "Wire")),                     # international wire (SWIFT or IBM AML "Wire")
        int(pay_type in ("Cash", "Cash Deposit")),              # cash transaction
        int(amount >= 470_000 and amount < 500_000),            # near 5L threshold
        int(amount >= 950_000 and amount < 1_000_000),          # near 10L threshold
        int(amount >= 2_400_000 and amount < 2_500_000),        # near 25L threshold
        int(amount > global_amount_p75),                        # above 75th percentile
        int(amount > global_amount_p95),                        # above 95th percentile
        np.log1p(amount) ** 2,                                  # squared log amount
    ], dtype=np.float32)


FEATURE_NAMES = [
    "log_amount", "hour", "is_night", "is_unsocial_hour",
    "currency_mismatch", "pay_currency_id", "rcv_currency_id",
    "payment_type_id", "cross_institution", "is_swift", "is_cash",
    "near_5l", "near_10l", "near_25l",
    "above_p75", "above_p95", "log_amount_sq",
]


def build_feature_matrix(df: pd.DataFrame, p75: float, p95: float) -> np.ndarray:
    """
    Vectorized 17-feature matrix for a batch of transactions.
    MUST stay in lockstep with _txn_features and the Kaggle training script.
    """
    amounts   = df["amount"].fillna(0).values.astype(float)
    pay_currs = df.get("payment_currency", pd.Series("INR", index=df.index)).fillna("INR").astype(str).str.strip().str.upper()
    rcv_currs = df.get("received_currency", pd.Series("INR", index=df.index)).fillna("INR").astype(str).str.strip().str.upper()
    pay_types = df.get("payment_type", pd.Series("NEFT", index=df.index)).fillna("NEFT").astype(str).str.strip()
    src_banks = df.get("sender_bank", pd.Series("", index=df.index)).fillna("").astype(str)
    dst_banks = df.get("receiver_bank", pd.Series("", index=df.index)).fillna("").astype(str)

    hours = pd.to_datetime(df["timestamp"], errors="coerce").dt.hour.fillna(12).values.astype(int)

    log_amt    = np.log1p(amounts)
    is_night   = (hours < 6).astype(np.float32)
    is_unsoc   = ((hours >= 22) | (hours < 6)).astype(np.float32)
    c_mismatch = (pay_currs.values != rcv_currs.values).astype(np.float32)
    pay_cid    = pay_currs.map(_CURRENCY_MAP).fillna(6).values.astype(np.float32)
    rcv_cid    = rcv_currs.map(_CURRENCY_MAP).fillna(6).values.astype(np.float32)
    pt_id      = pay_types.map(_PAYMENT_TYPE_MAP).fillna(8).values.astype(np.float32)
    cross_inst = ((src_banks.values != dst_banks.values)
                  & (src_banks.values != "") & (dst_banks.values != "")).astype(np.float32)
    is_swift   = pay_types.isin(["SWIFT", "Wire"]).values.astype(np.float32)
    is_cash    = pay_types.isin(["Cash", "Cash Deposit"]).values.astype(np.float32)
    near_5l    = ((amounts >= 470_000) & (amounts < 500_000)).astype(np.float32)
    near_10l   = ((amounts >= 950_000) & (amounts < 1_000_000)).astype(np.float32)
    near_25l   = ((amounts >= 2_400_000) & (amounts < 2_500_000)).astype(np.float32)
    above_p75  = (amounts > p75).astype(np.float32)
    above_p95  = (amounts > p95).astype(np.float32)

    return np.column_stack([
        log_amt, hours.astype(np.float32), is_night, is_unsoc,
        c_mismatch, pay_cid, rcv_cid, pt_id, cross_inst,
        is_swift, is_cash,
        near_5l, near_10l, near_25l,
        above_p75, above_p95, log_amt ** 2,
    ]).astype(np.float32)


def _build_txn_matrix(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    """Build (X, y) from the full transactions DataFrame."""
    p75 = float(df["amount"].quantile(0.75))
    p95 = float(df["amount"].quantile(0.95))
    X = build_feature_matrix(df, p75, p95)
    y = df["is_laundering"].fillna(0).astype(int).values
    return X, y


# ── Case-level aggregation from transaction scores ───────────────────────────

def _aggregate_txn_scores(scores: np.ndarray) -> Dict[str, float]:
    """Roll per-transaction probabilities up to a single case-level score."""
    if len(scores) == 0:
        return {"max": 0.0, "mean": 0.0, "frac_high": 0.0, "case_risk": 0.0}
    max_s   = float(scores.max())
    mean_s  = float(scores.mean())
    frac_h  = float((scores >= 0.5).mean())
    # Weighted combination — max dominates (one very suspicious txn = suspicious case)
    case_risk = max_s * 0.6 + mean_s * 0.3 + frac_h * 0.1
    return {"max": max_s, "mean": mean_s, "frac_high": frac_h, "case_risk": case_risk}


# ── XGBoost baseline ─────────────────────────────────────────────────────────

class XGBBaseline:
    """
    Transaction-level XGBoost model.

    fit_on_transactions(df)  — trains on raw transaction DataFrame
    predict_case(case_dict)  — returns case-level risk score in [0, 1]
    """

    def __init__(self):
        self.model          = None
        self._using_rf      = False
        self._p75           = 0.0
        self._p95           = 0.0
        self.eval_report    = {}

    # ── Training ──────────────────────────────────────────────────────────────

    def fit_on_transactions(self, df: pd.DataFrame, test_size: float = 0.2):
        """
        Train on individual transactions. Stratified split on is_laundering label.
        """
        X, y = _build_txn_matrix(df)
        self._p75 = float(df["amount"].quantile(0.75))
        self._p95 = float(df["amount"].quantile(0.95))

        pos = int(y.sum())
        neg = int(len(y) - pos)
        print(f"[xgb] Transaction-level dataset: {len(y):,} total, "
              f"{pos:,} positive ({100*pos/max(len(y),1):.2f}%), {neg:,} negative.")

        if pos < 2 or neg < 2:
            print("[xgb] Insufficient class balance — training on full set, no split.")
            self._fit_model(X, y)
            return

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, stratify=y, random_state=42
        )
        print(f"[xgb] Train: {len(y_train):,}  Test: {len(y_test):,}")

        self._fit_model(X_train, y_train)

        # Evaluate on held-out test transactions
        probs = self.model.predict_proba(X_test)[:, 1]
        preds = (probs >= 0.5).astype(int)
        try:
            auprc = average_precision_score(y_test, probs)
            auroc = roc_auc_score(y_test, probs)
        except Exception:
            auprc = auroc = float("nan")

        report = classification_report(y_test, preds, output_dict=True, zero_division=0)
        self.eval_report = {
            "level":       "transaction",
            "test_n":      int(len(y_test)),
            "test_pos":    int(y_test.sum()),
            "auprc":       round(auprc, 4),
            "auroc":       round(auroc, 4),
            "precision_1": round(report.get("1", {}).get("precision", 0), 4),
            "recall_1":    round(report.get("1", {}).get("recall", 0), 4),
            "f1_1":        round(report.get("1", {}).get("f1-score", 0), 4),
            "model":       "random_forest" if self._using_rf else "xgboost",
        }
        print(f"[xgb] Test (txn-level) AUPRC={auprc:.4f} AUROC={auroc:.4f} "
              f"P={self.eval_report['precision_1']:.4f} "
              f"R={self.eval_report['recall_1']:.4f} "
              f"F1={self.eval_report['f1_1']:.4f}")

    def _fit_model(self, X: np.ndarray, y: np.ndarray):
        pos = int(y.sum())
        neg = int(len(y) - pos)
        scale_pos_weight = neg / max(pos, 1)

        try:
            from xgboost import XGBClassifier

            # Validation split for early stopping
            if len(y) >= 20 and pos >= 2:
                X_tr, X_val, y_tr, y_val = train_test_split(
                    X, y, test_size=0.15, stratify=y, random_state=42
                )
                eval_set = [(X_val, y_val)]
            else:
                X_tr, y_tr = X, y
                eval_set = None

            self.model = XGBClassifier(
                n_estimators=500,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                min_child_weight=5,
                gamma=1,
                scale_pos_weight=scale_pos_weight,
                eval_metric="aucpr",
                early_stopping_rounds=30 if eval_set else None,
                random_state=42,
                n_jobs=-1,
            )
            self.model.fit(X_tr, y_tr, eval_set=eval_set, verbose=False)
            self._using_rf = False

            imp = self.model.feature_importances_
            top5 = np.argsort(imp)[::-1][:5]
            print(f"[xgb] Trained XGBoost (scale_pos_weight={scale_pos_weight:.1f}). "
                  f"Top features: {[FEATURE_NAMES[i] for i in top5]}")

        except ImportError:
            print("[xgb] XGBoost not installed — using RandomForest fallback.")
            from sklearn.ensemble import RandomForestClassifier
            self.model = RandomForestClassifier(
                n_estimators=300,
                max_depth=8,
                class_weight="balanced",
                random_state=42,
                n_jobs=-1,
            )
            self.model.fit(X, y)
            self._using_rf = True

    # ── Inference ─────────────────────────────────────────────────────────────

    def score_transactions(self, df: pd.DataFrame) -> np.ndarray:
        """
        Vectorized per-transaction scoring — the Phase 4 primary path.
        Returns an array of laundering probabilities aligned with df rows.
        """
        if self.model is None or len(df) == 0:
            return np.zeros(len(df), dtype=np.float32)
        X = build_feature_matrix(df, self._p75, self._p95)
        return self.model.predict_proba(X)[:, 1].astype(np.float32)

    def adapt(self, df: pd.DataFrame, n_new_trees: int = 50) -> bool:
        """
        Drift response: continue boosting on the current run's labeled
        transactions, warm-starting from the existing booster. The pretrained
        trees are kept; n_new_trees new trees are fitted on the drifted data,
        shifting the ensemble toward the current distribution.
        Saves the adapted model to xgb_adapted.json. Returns True on success.
        """
        if self.model is None or "is_laundering" not in df.columns:
            return False
        y = df["is_laundering"].fillna(0).astype(int).values
        if y.sum() < 2 or (len(y) - y.sum()) < 2:
            print("[xgb] adapt: not enough labeled examples of both classes — skipping.")
            return False

        try:
            from xgboost import XGBClassifier
            X = build_feature_matrix(df, self._p75, self._p95)
            scale_pos_weight = (len(y) - y.sum()) / max(int(y.sum()), 1)

            adapted = XGBClassifier(
                n_estimators=n_new_trees,
                max_depth=6,
                learning_rate=0.05,
                subsample=0.8,
                colsample_bytree=0.8,
                min_child_weight=5,
                gamma=1,
                scale_pos_weight=scale_pos_weight,
                eval_metric="aucpr",
                random_state=42,
                n_jobs=-1,
            )
            adapted.fit(X, y, xgb_model=self.model.get_booster())
            self.model = adapted
            self.model.save_model(XGB_ADAPTED_PATH)
            print(f"[xgb] Drift adaptation: +{n_new_trees} trees warm-started on "
                  f"{len(y):,} current transactions ({int(y.sum())} positive). "
                  f"Saved to {XGB_ADAPTED_PATH}")
            return True
        except Exception as e:
            print(f"[xgb] adapt failed ({e}) — continuing with the frozen pretrained model.")
            return False

    def predict_case(self, case_dict: Dict) -> float:
        """
        Score a case by running the transaction-level model on each of its
        transactions, then aggregating.
        Returns a single float in [0, 1].
        """
        if self.model is None:
            return 0.5

        txns = case_dict.get("transactions", [])
        if isinstance(txns, pd.DataFrame):
            rows_iter = (row for _, row in txns.iterrows())
            n = len(txns)
        else:
            rows_iter = txns
            n = len(txns)

        if n == 0:
            return 0.0

        feats = []
        for row in rows_iter:
            if isinstance(row, dict):
                row = pd.Series(row)
            feats.append(_txn_features(row, self._p75, self._p95))

        X = np.array(feats, dtype=np.float32)
        scores = self.model.predict_proba(X)[:, 1]
        return _aggregate_txn_scores(scores)["case_risk"]

    # For backward compat with compare.py
    def predict_proba(self, case_dict: Dict) -> float:
        return self.predict_case(case_dict)

    def predict_proba_vec(self, x: np.ndarray) -> float:
        return float(self.model.predict_proba(x.reshape(1, -1))[0, 1])

    # ── Persistence ───────────────────────────────────────────────────────────

    def save(self):
        os.makedirs(MODELS_DIR, exist_ok=True)
        with open(XGB_PATH, "wb") as f:
            pickle.dump(self, f)
        print(f"[xgb] Saved to {XGB_PATH}")

    @classmethod
    def load(cls) -> "XGBBaseline":
        # Prefer Kaggle-trained native JSON (no import-path issues) over local pkl
        if os.path.exists(XGB_JSON_PATH) and os.path.exists(XGB_META_PATH):
            return cls.load_pretrained(XGB_JSON_PATH, XGB_META_PATH)
        with open(XGB_PATH, "rb") as f:
            return pickle.load(f)

    @classmethod
    def load_pretrained(cls, json_path: str = None, meta_path: str = None) -> "XGBBaseline":
        """
        Load a model exported from Kaggle (or any external training run).
        Uses XGBoost's native JSON format — no pickle class-path issues.

        Expected files:
          xgb_pretrained.json      — saved with model.save_model(path)
          xgb_pretrained_meta.json — {"p75": float, "p95": float, "eval_report": {...}}
        """
        import json as _json
        from xgboost import XGBClassifier

        json_path = json_path or XGB_JSON_PATH
        meta_path = meta_path or XGB_META_PATH

        obj = cls()
        obj.model = XGBClassifier()
        # Prefer the drift-adapted model when present (pretrained trees + adaptation trees)
        if json_path == XGB_JSON_PATH and os.path.exists(XGB_ADAPTED_PATH):
            print("[xgb] Drift-adapted model found — loading it instead of the frozen pretrained.")
            json_path = XGB_ADAPTED_PATH
        obj.model.load_model(json_path)
        with open(meta_path) as f:
            meta = _json.load(f)
        obj._p75         = float(meta.get("p75", 0.0))
        obj._p95         = float(meta.get("p95", 0.0))
        obj._using_rf    = False
        obj.eval_report  = meta.get("eval_report", {})
        print(f"[xgb] Loaded pretrained model from {json_path}  "
              f"(AUPRC={obj.eval_report.get('auprc', 'n/a')})")
        return obj

    @classmethod
    def is_trained(cls) -> bool:
        return (
            os.path.exists(XGB_PATH)
            or (os.path.exists(XGB_JSON_PATH) and os.path.exists(XGB_META_PATH))
        )


# ── Rule-count baseline ───────────────────────────────────────────────────────

def rule_count_score(case_dict: Dict) -> float:
    """Naive baseline: normalised alert count. Zero parameters."""
    n_alerts = len(case_dict.get("member_alert_ids", []))
    return min(1.0, n_alerts / 10.0)


# ── PR curve helper ───────────────────────────────────────────────────────────

def get_baselines_pr(
    xgb: XGBBaseline,
    case_dicts: List[Dict],
    labels: List[int],
) -> Tuple[List[Dict], List[Dict]]:
    xgb_probs = np.array([xgb.predict_case(c) for c in case_dicts])
    rc_probs  = np.array([rule_count_score(c) for c in case_dicts])
    y = np.array(labels)

    def _pr(probs):
        prec, rec, thresh = precision_recall_curve(y, probs)
        return [
            {"precision": float(p), "recall": float(r), "threshold": float(t)}
            for p, r, t in zip(prec[:-1], rec[:-1], thresh)
        ]

    return _pr(xgb_probs), _pr(rc_probs)
