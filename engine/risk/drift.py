"""
Drift Watchdog — runs alongside Phase 4 (XGBoost scoring).

The pretrained XGBoost is a frozen artifact from Kaggle. This watchdog checks
whether the live transactions still look like the training distribution, using
the baseline the Kaggle export already ships (amount p75/p95 in
xgb_pretrained_meta.json):

  1. PSI (Population Stability Index) on the amount distribution, using the
     baseline p75/p95 as bin edges. By construction the baseline proportions
     in the bins [0, p75), [p75, p95), [p95, inf) are [0.75, 0.20, 0.05].
  2. Score-distribution sanity: mean and high-score fraction of the live
     xgb_score distribution (a frozen model on shifted data typically pushes
     scores toward extremes).

If drift is detected, seed.py responds by warm-starting additional boosting
rounds on the current run's labeled transactions (XGBBaseline.adapt) — the
"dynamic weight update" path. Detection itself never mutates Phase 4 output.

PSI rule of thumb: < 0.10 stable, 0.10-0.25 moderate shift, > 0.25 major shift.
"""

from typing import Dict

import numpy as np
import pandas as pd

PSI_DRIFT_THRESHOLD = 0.25
BASELINE_BIN_PROPS = np.array([0.75, 0.20, 0.05])


def _psi(expected: np.ndarray, actual: np.ndarray) -> float:
    eps = 1e-6
    expected = np.clip(expected, eps, None)
    actual = np.clip(actual, eps, None)
    return float(np.sum((actual - expected) * np.log(actual / expected)))


def check_drift(df: pd.DataFrame, scores: np.ndarray, baseline_p75: float, baseline_p95: float) -> Dict:
    """
    Compare the live run's amounts and xgb_scores against the Kaggle baseline.
    Returns a report dict: {psi, drifted, live_p75, live_p95, score_mean, ...}.
    """
    amounts = df["amount"].fillna(0).values.astype(float)

    if baseline_p75 <= 0 or baseline_p95 <= baseline_p75 or len(amounts) == 0:
        return {"drifted": False, "psi": 0.0, "note": "no baseline or no data — drift check skipped"}

    live_props = np.array([
        float((amounts < baseline_p75).mean()),
        float(((amounts >= baseline_p75) & (amounts < baseline_p95)).mean()),
        float((amounts >= baseline_p95).mean()),
    ])
    psi = _psi(BASELINE_BIN_PROPS, live_props)

    live_p75 = float(np.percentile(amounts, 75))
    live_p95 = float(np.percentile(amounts, 95))
    score_mean = float(scores.mean()) if len(scores) else 0.0
    score_high_frac = float((scores >= 0.5).mean()) if len(scores) else 0.0

    drifted = psi > PSI_DRIFT_THRESHOLD

    report = {
        "psi":             round(psi, 4),
        "psi_threshold":   PSI_DRIFT_THRESHOLD,
        "drifted":         drifted,
        "baseline_p75":    round(baseline_p75, 2),
        "baseline_p95":    round(baseline_p95, 2),
        "live_p75":        round(live_p75, 2),
        "live_p95":        round(live_p95, 2),
        "live_bin_props":  [round(x, 4) for x in live_props],
        "score_mean":      round(score_mean, 4),
        "score_high_frac": round(score_high_frac, 4),
    }

    if drifted:
        print(f"[drift] DRIFT DETECTED — PSI={psi:.3f} (>{PSI_DRIFT_THRESHOLD}). "
              f"Live amount p75={live_p75:,.0f} vs baseline {baseline_p75:,.0f}. "
              f"Triggering warm-start adaptation of the XGBoost ensemble.")
    else:
        print(f"[drift] Stable — PSI={psi:.3f} (threshold {PSI_DRIFT_THRESHOLD}). "
              f"Frozen pretrained model remains valid for this data.")

    return report
