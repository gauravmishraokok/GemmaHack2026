"""
Comparison table: Gemma probe vs XGBoost vs rule-count.

Uses the same held-out test indices for all three models so the comparison
is apples-to-apples. Results feed the PR-AUC chart in the frontend.
"""

import numpy as np
from typing import List, Dict

from sklearn.metrics import average_precision_score, roc_auc_score, precision_recall_curve
from sklearn.model_selection import train_test_split

from engine.risk.probe import GemmaProbe
from engine.risk.baselines import XGBBaseline, rule_count_score


def compute_comparison(
    probe: GemmaProbe,
    xgb: XGBBaseline,
    case_dicts: List[Dict],
    labels: List[int],
    test_size: float = 0.2,
    random_state: int = 42,
) -> List[Dict]:
    """
    Evaluate all three models on the same held-out test split.
    Returns List[ComparisonMetric-compatible dicts] at each model's F1-optimal threshold.

    Falls back to full-dataset evaluation if there's insufficient data for a split.
    """
    y = np.array(labels)
    n = len(y)
    pos = int(y.sum())
    neg = n - pos

    can_split = pos >= 4 and neg >= 4 and n >= 10

    if can_split:
        idx = np.arange(n)
        idx_train, idx_test = train_test_split(
            idx, test_size=test_size, stratify=y, random_state=random_state
        )
        eval_cases  = [case_dicts[i] for i in idx_test]
        eval_labels = y[idx_test]
        print(f"[compare] Evaluating on held-out test set: "
              f"{len(idx_test)} cases ({int(eval_labels.sum())} positive)")
    else:
        print(f"[compare] Insufficient data for split (n={n}, pos={pos}). "
              f"Evaluating on full set — metrics are optimistic.")
        eval_cases  = case_dicts
        eval_labels = y

    results = []

    def _f1_optimal_point(probs: np.ndarray, y_true: np.ndarray) -> Dict:
        try:
            auprc = float(average_precision_score(y_true, probs))
            auroc = float(roc_auc_score(y_true, probs))
        except Exception:
            auprc = auroc = float("nan")

        prec, rec, thresholds = precision_recall_curve(y_true, probs)
        if len(thresholds) == 0:
            return {"precision": 0.0, "recall": 0.0, "threshold": 0.5,
                    "auprc": auprc, "auroc": auroc}

        f1s  = 2 * prec[:-1] * rec[:-1] / (prec[:-1] + rec[:-1] + 1e-9)
        best = int(np.argmax(f1s))
        return {
            "precision": round(float(prec[best]),       4),
            "recall":    round(float(rec[best]),        4),
            "threshold": round(float(thresholds[best]), 4),
            "auprc":     round(auprc, 4),
            "auroc":     round(auroc, 4),
        }

    # ── Gemma probe ──────────────────────────────────────────────────────────
    try:
        probe_probs = np.array([probe.predict(c)[0] for c in eval_cases])
        pt = _f1_optimal_point(probe_probs, eval_labels)
        results.append({"model": "gemma_probe", **pt})
        print(f"[compare] gemma_probe: AUPRC={pt['auprc']:.4f} "
              f"P={pt['precision']:.4f} R={pt['recall']:.4f}")
    except Exception as e:
        print(f"[compare] Probe eval failed: {e}")
        results.append({"model": "gemma_probe",
                        "precision": 0.0, "recall": 0.0, "threshold": 0.5,
                        "auprc": 0.0, "auroc": 0.0})

    # ── XGBoost (transaction-level aggregation) ───────────────────────────────
    try:
        xgb_probs = np.array([xgb.predict_case(c) for c in eval_cases])
        xt = _f1_optimal_point(xgb_probs, eval_labels)
        results.append({"model": "xgboost", **xt})
        print(f"[compare] xgboost:    AUPRC={xt['auprc']:.4f} "
              f"P={xt['precision']:.4f} R={xt['recall']:.4f}")
    except Exception as e:
        print(f"[compare] XGBoost eval failed: {e}")
        results.append({"model": "xgboost",
                        "precision": 0.0, "recall": 0.0, "threshold": 0.5,
                        "auprc": 0.0, "auroc": 0.0})

    # ── Rule count ────────────────────────────────────────────────────────────
    try:
        rc_probs = np.array([rule_count_score(c) for c in eval_cases])
        rt = _f1_optimal_point(rc_probs, eval_labels)
        results.append({"model": "rule_count", **rt})
        print(f"[compare] rule_count: AUPRC={rt['auprc']:.4f} "
              f"P={rt['precision']:.4f} R={rt['recall']:.4f}")
    except Exception as e:
        print(f"[compare] Rule-count eval failed: {e}")
        results.append({"model": "rule_count",
                        "precision": 0.0, "recall": 0.0, "threshold": 0.5,
                        "auprc": 0.0, "auroc": 0.0})

    return results
