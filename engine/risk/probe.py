"""
Gemma activation probe — production version.

Pipeline:
  1. Convert each Case to a rich natural-language description
  2. Extract mid-layer hidden states from google/gemma-3-1b-it (transformers)
     Model: 1B params, bfloat16 (~2 GB RAM) — fits on 16 GB dev machines.
     (gemma-3-4b-it needs 16 GB+ and segfaults with typical available memory.)
  3. Mean-pool → 1152-dim vector per case
  4. PCA to 64 dims (avoids n << p overfitting with small case counts)
  5. LogisticRegressionCV — selects C via stratified inner CV (falls back to
     fixed-C LR when fewer than 4 positive cases are available)
  6. Evaluate on held-out test split, never on training data
  7. Mahalanobis OOD from training centroid in PCA space

Activations are cached to disk. Gemma is loaded once, then freed.
Set USE_GEMMA=0 to use the TF-IDF fallback (no GPU needed).
"""

import os
import pickle
import hashlib
import numpy as np
import pandas as pd
from typing import List, Dict, Optional, Tuple

from sklearn.linear_model import LogisticRegressionCV
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
from sklearn.metrics import (
    precision_recall_curve, roc_auc_score, average_precision_score, classification_report
)
from sklearn.model_selection import StratifiedKFold

CACHE_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "probe_cache")
PROBE_PATH = os.path.join(CACHE_DIR, "probe_model.pkl")
GEMMA_MODEL_ID = "google/gemma-3-1b-it"   # 1B fits on 16GB RAM; 4B needs 16GB+ and OOMs
USE_GEMMA_ENV = os.environ.get("USE_GEMMA", "1")

# PCA target dimensionality — keeps variance high while controlling n << p overfitting
PCA_COMPONENTS = 64


# ---- Case → text description -------------------------------------------------

def _case_to_text(case_dict: Dict) -> str:
    """
    Rich natural-language description of a case for the probe.
    Sees everything Phase 6 assembled: transaction patterns, per-txn XGBoost
    scores, KYC red flags, shared PAN groups, and rule alerts.
    """
    accounts = case_dict.get("accounts", [])
    txns = case_dict.get("transactions", [])

    if isinstance(txns, pd.DataFrame):
        amounts     = txns["amount"].values if "amount" in txns.columns else np.array([0.0])
        currencies  = set(txns["payment_currency"].dropna().unique()) if "payment_currency" in txns.columns else set()
        rcurrencies = set(txns.get("received_currency", pd.Series(dtype=object)).dropna().unique())
        timestamps  = pd.to_datetime(txns["timestamp"], errors="coerce") if "timestamp" in txns.columns else pd.Series(dtype="datetime64[ns]")
        xgb_scores  = txns["xgb_score"].values if "xgb_score" in txns.columns else np.array([])
    else:
        amounts     = np.array([t.get("amount", 0) for t in txns]) if txns else np.array([0.0])
        currencies  = {t.get("currency", t.get("payment_currency", "INR")) for t in txns}
        rcurrencies = set()
        timestamps  = pd.Series(dtype="datetime64[ns]")
        xgb_scores  = np.array([t.get("xgb_score") for t in txns if t.get("xgb_score") is not None])

    total_amount = float(amounts.sum())
    mean_amount  = float(amounts.mean()) if len(amounts) else 0.0
    max_amount   = float(amounts.max()) if len(amounts) else 0.0
    txn_count    = len(amounts)
    cross_curr   = len(currencies | rcurrencies) > 1
    night_txns   = int((timestamps.dt.hour < 6).sum()) if len(timestamps) else 0

    xgb_max  = float(xgb_scores.max()) if len(xgb_scores) else 0.0
    xgb_mean = float(xgb_scores.mean()) if len(xgb_scores) else 0.0

    # KYC red flags
    kyc = case_dict.get("kyc", {})
    failed_kyc  = sum(1 for r in kyc.values() if r.get("kyc_status") == "FAILED")
    pending_kyc = sum(1 for r in kyc.values() if r.get("kyc_status") == "PENDING")
    shell_cos   = sum(1 for r in kyc.values() if r.get("entity_subtype") == "Shell Company")
    high_risk_j = sum(1 for r in kyc.values() if r.get("jurisdiction") == "High Risk")

    # Shared PAN groups — one beneficial owner controlling multiple accounts
    spg = case_dict.get("shared_pan_groups", [])
    spg_str = "; ".join(
        f"{len(g['accounts'])} accounts share PAN {g['pan']}" for g in spg
    ) or "none"

    # Rule alerts
    alert_details = case_dict.get("alert_details", [])
    alert_types = sorted({a.get("alert_type", "") for a in alert_details if a.get("alert_type")})
    curr_str = ", ".join(sorted(str(c) for c in (currencies | rcurrencies))) or "unknown"

    return (
        f"Financial crime case with {len(accounts)} accounts and {txn_count} transactions. "
        f"Total value: {total_amount:,.0f}. Mean: {mean_amount:,.0f}. Max: {max_amount:,.0f}. "
        f"ML anomaly scores: max {xgb_max:.2f}, mean {xgb_mean:.2f}. "
        f"Shared PAN groups (one owner, multiple accounts): {spg_str}. "
        f"KYC red flags: {failed_kyc} FAILED, {pending_kyc} PENDING, "
        f"{shell_cos} shell companies, {high_risk_j} high-risk jurisdictions. "
        f"Rule alerts ({len(alert_details)}): {', '.join(alert_types) or 'none'}. "
        f"Currencies involved: {curr_str}. Cross-currency: {cross_curr}. "
        f"Night-time transactions (00:00-06:00): {night_txns}."
    )


# ---- Activation extraction ---------------------------------------------------

def _hash_texts(texts: List[str]) -> str:
    return hashlib.md5("||".join(texts).encode()).hexdigest()


def _extract_gemma_activations(texts: List[str]) -> Optional[np.ndarray]:
    """
    Load Gemma 1B once, extract mid-layer hidden states for all texts, free memory.
    Returns (N, hidden_dim) float32 array or None if Gemma is unavailable.

    Model choice: gemma-3-1b-it (~2GB in bfloat16) fits in 16GB RAM.
    gemma-3-4b-it needs 16GB+ in float32 and OOMs on typical dev machines.
    output_hidden_states is passed at inference time (not in from_pretrained).
    """
    if USE_GEMMA_ENV == "0":
        return None
    try:
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM

        on_gpu = torch.cuda.is_available()
        # bfloat16 halves memory on both CPU and GPU; supported since PyTorch 1.10
        dtype = torch.bfloat16

        print(f"[probe] Loading {GEMMA_MODEL_ID} ({'GPU' if on_gpu else 'CPU'}, {dtype}) ...")
        tok = AutoTokenizer.from_pretrained(GEMMA_MODEL_ID)

        # No device_map — load directly to target device, no accelerate needed
        model = AutoModelForCausalLM.from_pretrained(
            GEMMA_MODEL_ID,
            dtype=dtype,            # 'dtype' (not deprecated 'torch_dtype')
        )
        if on_gpu:
            model = model.cuda()
        model.eval()

        n_layers = model.config.num_hidden_layers
        mid_layer = n_layers // 2
        print(f"[probe] Model loaded. Extracting layer {mid_layer}/{n_layers} "
              f"hidden states for {len(texts)} cases ...")

        vectors = []
        with torch.no_grad():
            for i, text in enumerate(texts):
                inputs = tok(
                    text, return_tensors="pt",
                    truncation=True, max_length=256,
                )
                if on_gpu:
                    inputs = {k: v.cuda() for k, v in inputs.items()}

                # output_hidden_states at forward() time, not in from_pretrained
                out = model(**inputs, output_hidden_states=True)
                hidden = out.hidden_states[mid_layer]       # (1, seq_len, hidden_dim)
                pooled = hidden[0].mean(dim=0).cpu().float().numpy()
                vectors.append(pooled)
                if (i + 1) % 10 == 0:
                    print(f"[probe]   {i+1}/{len(texts)} done")

        del model
        if on_gpu:
            torch.cuda.empty_cache()

        result = np.array(vectors, dtype=np.float32)
        print(f"[probe] Extracted activations shape: {result.shape}")
        return result

    except Exception as e:
        print(f"[probe] Gemma unavailable ({e}), falling back to TF-IDF.")
        return None


def _extract_tfidf_activations(texts: List[str], vectorizer=None) -> Tuple[np.ndarray, object]:
    from sklearn.feature_extraction.text import TfidfVectorizer
    if vectorizer is None:
        vectorizer = TfidfVectorizer(max_features=1024, ngram_range=(1, 2), sublinear_tf=True)
        X = vectorizer.fit_transform(texts).toarray()
    else:
        X = vectorizer.transform(texts).toarray()
    return X.astype(np.float32), vectorizer


# ---- Cached activation loader ------------------------------------------------

def _load_or_extract(texts: List[str], tfidf_vec=None) -> Tuple[np.ndarray, Optional[object]]:
    """
    Returns (activations, updated_tfidf_vec).
    Checks cache first; falls back to Gemma then TF-IDF.
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_key = _hash_texts(texts)
    cache_file = os.path.join(CACHE_DIR, f"act_{cache_key}.npy")

    if os.path.exists(cache_file):
        print(f"[probe] Loading cached activations from {cache_file}")
        return np.load(cache_file), tfidf_vec

    vecs = _extract_gemma_activations(texts)
    if vecs is not None:
        np.save(cache_file, vecs)
        return vecs, None   # Gemma mode: no tfidf_vec

    vecs, tfidf_vec = _extract_tfidf_activations(texts, tfidf_vec)
    np.save(cache_file, vecs)
    return vecs, tfidf_vec


# ---- Main probe class --------------------------------------------------------

class GemmaProbe:
    """
    Gemma hidden-state probe with PCA + LogisticRegressionCV.

    Attributes set after .fit():
        use_gemma      — whether Gemma activations were used
        pca            — fitted PCA (64 components)
        scaler         — fitted StandardScaler (applied before PCA)
        lr             — fitted LogisticRegressionCV
        train_centroid — mean of PCA-projected training vectors (for OOD)
        train_cov_inv  — pseudo-inverse covariance (for Mahalanobis OOD)
        tfidf_vec      — TF-IDF vectorizer if used instead of Gemma
        eval_report    — dict with test-set metrics (set by fit_with_split)
    """

    def __init__(self):
        self.use_gemma      = False
        self.pca            = None
        self.scaler         = None
        self.lr             = None
        self.train_centroid = None
        self.train_cov_inv  = None
        self.tfidf_vec      = None
        self.eval_report    = {}

    # ---- Training ------------------------------------------------------------

    def fit(self, case_dicts: List[Dict], labels: List[int]):
        """
        Train on all provided cases (no split). Use fit_with_split for proper evaluation.
        """
        texts = [_case_to_text(c) for c in case_dicts]
        X_raw, self.tfidf_vec = _load_or_extract(texts, self.tfidf_vec)
        self.use_gemma = self.tfidf_vec is None
        self._fit_model(X_raw, np.array(labels))

    def fit_with_split(
        self,
        case_dicts: List[Dict],
        labels: List[int],
        test_size: float = 0.2,
        val_size: float = 0.1,
        random_state: int = 42,
    ):
        """
        Stratified train/val/test split → fit on train → evaluate on test.
        Sets self.eval_report with held-out metrics.
        """
        from sklearn.model_selection import train_test_split

        labels_arr = np.array(labels)
        n = len(labels_arr)

        # Need at least 2 samples of each class for stratification
        pos = labels_arr.sum()
        neg = n - pos
        if pos < 2 or neg < 2:
            print(f"[probe] WARNING: Only {pos} positive / {neg} negative cases. "
                  f"Falling back to no-split training.")
            self.fit(case_dicts, labels)
            return

        # Split: first carve off test, then val from the remaining train
        idx = np.arange(n)
        idx_trainval, idx_test = train_test_split(
            idx, test_size=test_size, stratify=labels_arr, random_state=random_state
        )
        labels_trainval = labels_arr[idx_trainval]

        if val_size > 0 and len(idx_trainval) > 4:
            val_fraction = val_size / (1 - test_size)
            idx_train, idx_val = train_test_split(
                idx_trainval, test_size=val_fraction,
                stratify=labels_trainval, random_state=random_state,
            )
        else:
            idx_train = idx_trainval
            idx_val = np.array([], dtype=int)

        print(f"[probe] Split: train={len(idx_train)} val={len(idx_val)} test={len(idx_test)} "
              f"(pos in train: {labels_arr[idx_train].sum()}, test: {labels_arr[idx_test].sum()})")

        # Extract activations for all cases at once (single Gemma pass)
        texts = [_case_to_text(c) for c in case_dicts]
        X_all, self.tfidf_vec = _load_or_extract(texts, self.tfidf_vec)
        self.use_gemma = self.tfidf_vec is None

        X_train = X_all[idx_train]
        y_train = labels_arr[idx_train]
        X_test  = X_all[idx_test]
        y_test  = labels_arr[idx_test]

        self._fit_model(X_train, y_train)

        # Evaluate on held-out test set
        if len(y_test) > 0 and y_test.sum() > 0:
            X_test_proj = self._project(X_test)
            probs = self.lr.predict_proba(X_test_proj)[:, 1]
            preds = (probs >= 0.5).astype(int)

            try:
                auprc = average_precision_score(y_test, probs)
                auroc = roc_auc_score(y_test, probs)
            except Exception:
                auprc = auroc = float("nan")

            report = classification_report(y_test, preds, output_dict=True, zero_division=0)
            self.eval_report = {
                "test_n": int(len(y_test)),
                "test_pos": int(y_test.sum()),
                "auprc": round(auprc, 4),
                "auroc": round(auroc, 4),
                "precision_1": round(report.get("1", {}).get("precision", 0), 4),
                "recall_1":    round(report.get("1", {}).get("recall", 0), 4),
                "f1_1":        round(report.get("1", {}).get("f1-score", 0), 4),
                "source": "gemma_probe" if self.use_gemma else "tfidf_probe",
            }
            print(f"[probe] Test AUPRC={auprc:.4f} AUROC={auroc:.4f} "
                  f"P={self.eval_report['precision_1']:.4f} "
                  f"R={self.eval_report['recall_1']:.4f} "
                  f"F1={self.eval_report['f1_1']:.4f}")
        else:
            print("[probe] Test set has no positives — cannot compute AUPRC/AUROC.")
            self.eval_report = {"note": "insufficient_test_positives"}

    def _fit_model(self, X: np.ndarray, y: np.ndarray):
        """Scale → PCA → LogisticRegressionCV → centroid/covariance for OOD."""
        # Scale
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        # PCA — cap components at min(n_samples-1, PCA_COMPONENTS)
        n_components = min(PCA_COMPONENTS, X_scaled.shape[0] - 1, X_scaled.shape[1])
        self.pca = PCA(n_components=n_components, random_state=42)
        X_pca = self.pca.fit_transform(X_scaled)
        var_explained = self.pca.explained_variance_ratio_.sum()
        print(f"[probe] PCA: {n_components} components explain {var_explained:.1%} variance.")

        # OOD reference (computed in PCA space)
        self.train_centroid = X_pca.mean(axis=0)
        try:
            cov = np.cov(X_pca.T)
            self.train_cov_inv = np.linalg.pinv(cov)
        except Exception:
            self.train_cov_inv = np.eye(X_pca.shape[1])

        n_pos = int(y.sum())
        if n_pos >= 4:
            # Enough positives for proper inner CV
            n_splits = min(5, n_pos)
            cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
            self.lr = LogisticRegressionCV(
                Cs=10,
                cv=cv,
                scoring="average_precision",
                class_weight="balanced",
                max_iter=2000,
                random_state=42,
                n_jobs=-1,
            )
            self.lr.fit(X_pca, y)
            best_C = self.lr.C_[0]
            print(f"[probe] LogisticRegressionCV best C={best_C:.4f} "
                  f"(trained on {len(y)} cases, use_gemma={self.use_gemma}).")
        else:
            # Too few positives for CV — use fixed-C logistic regression
            from sklearn.linear_model import LogisticRegression
            print(f"[probe] Only {n_pos} positive sample(s) — skipping CV, "
                  f"using fixed C=0.01 logistic regression.")
            self.lr = LogisticRegression(
                C=0.01,
                class_weight="balanced",
                max_iter=2000,
                random_state=42,
            )
            self.lr.fit(X_pca, y)
            # Wrap with a .C_ attribute so downstream code stays consistent
            self.lr.C_ = np.array([0.01])

    def _project(self, X: np.ndarray) -> np.ndarray:
        """Scale + PCA-project raw activations."""
        return self.pca.transform(self.scaler.transform(X))

    # ---- Inference -----------------------------------------------------------

    def predict(self, case_dict: Dict) -> Tuple[float, float, float]:
        """
        Returns (p, margin, ood).
        Uses cached activations if available; otherwise extracts on-the-fly.
        """
        if self.lr is None:
            raise RuntimeError("Probe not trained. Call fit() or fit_with_split() first.")

        text = _case_to_text(case_dict)
        os.makedirs(CACHE_DIR, exist_ok=True)
        cache_key = _hash_texts([text])
        cache_file = os.path.join(CACHE_DIR, f"act_{cache_key}.npy")

        if os.path.exists(cache_file):
            vec = np.load(cache_file)
        else:
            if self.use_gemma:
                vec = _extract_gemma_activations([text])
                if vec is None:
                    raise RuntimeError("Probe was trained with Gemma but Gemma is now unavailable.")
            else:
                vec, _ = _extract_tfidf_activations([text], self.tfidf_vec)
            np.save(cache_file, vec)

        X_pca = self._project(vec)
        p = float(self.lr.predict_proba(X_pca)[0, 1])
        margin = abs(p - 0.5) * 2

        diff = X_pca[0] - self.train_centroid
        try:
            ood = float(np.sqrt(np.clip(diff @ self.train_cov_inv @ diff, 0, None)))
        except Exception:
            ood = float(np.linalg.norm(diff))

        return p, margin, ood

    # ---- Persistence ---------------------------------------------------------

    def save(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(PROBE_PATH, "wb") as f:
            pickle.dump(self, f)
        print(f"[probe] Saved to {PROBE_PATH}")

    @classmethod
    def load(cls) -> "GemmaProbe":
        with open(PROBE_PATH, "rb") as f:
            return pickle.load(f)

    @classmethod
    def is_trained(cls) -> bool:
        return os.path.exists(PROBE_PATH)


# ---- PR curve helper ---------------------------------------------------------

def get_precision_recall(
    probe: "GemmaProbe",
    case_dicts: List[Dict],
    labels: List[int],
) -> List[Dict]:
    """PR curve data at all thresholds, for the comparison chart."""
    texts = [_case_to_text(c) for c in case_dicts]
    X_all, _ = _load_or_extract(texts, probe.tfidf_vec)
    X_pca = probe._project(X_all)
    probs = probe.lr.predict_proba(X_pca)[:, 1]
    y = np.array(labels)
    precisions, recalls, thresholds = precision_recall_curve(y, probs)
    return [
        {"precision": float(p), "recall": float(r), "threshold": float(t)}
        for p, r, t in zip(precisions[:-1], recalls[:-1], thresholds)
    ]
