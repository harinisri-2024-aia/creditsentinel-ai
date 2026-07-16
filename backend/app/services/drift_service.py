import numpy as np
import pandas as pd
from app.services.ml_service import FEATURE_COLUMNS, get_dataset

DRIFT_THRESHOLD = 0.15  # PSI-like threshold per feature
DRIFT_RATIO_TRIGGER = 0.3  # fraction of features drifted to trigger retrain


def _population_stability_index(reference: np.ndarray, current: np.ndarray, bins: int = 10) -> float:
    """Simplified PSI calculation between two numeric distributions."""
    breakpoints = np.linspace(0, 100, bins + 1)
    ref_pct = np.percentile(reference, breakpoints)
    ref_pct[0], ref_pct[-1] = -np.inf, np.inf

    ref_counts, _ = np.histogram(reference, bins=ref_pct)
    cur_counts, _ = np.histogram(current, bins=ref_pct)

    ref_dist = ref_counts / max(len(reference), 1) + 1e-6
    cur_dist = cur_counts / max(len(current), 1) + 1e-6

    psi = np.sum((cur_dist - ref_dist) * np.log(cur_dist / ref_dist))
    return float(abs(psi))


def simulate_production_batch(drift_intensity: float = 0.0, n: int = 800, seed: int = None):
    """Simulate a new incoming production batch, optionally shifted to emulate drift."""
    seed = seed if seed is not None else np.random.randint(0, 100000)
    df = get_dataset()
    sample = df.sample(n=min(n, len(df)), random_state=seed).copy()

    if drift_intensity > 0:
        rng = np.random.default_rng(seed)
        sample["credit_score"] = sample["credit_score"] - drift_intensity * 120
        sample["annual_income"] = sample["annual_income"] * (1 - drift_intensity * 0.3)
        sample["existing_debt"] = sample["existing_debt"] * (1 + drift_intensity * 0.6)
        sample["loan_amount"] = sample["loan_amount"] * (1 + drift_intensity * 0.4)

    return sample


def run_drift_detection(reference_df: pd.DataFrame, current_df: pd.DataFrame):
    drifted_features = []
    feature_scores = {}

    for feature in FEATURE_COLUMNS:
        psi = _population_stability_index(
            reference_df[feature].values.astype(float),
            current_df[feature].values.astype(float),
        )
        feature_scores[feature] = round(psi, 4)
        if psi > DRIFT_THRESHOLD:
            drifted_features.append(feature)

    data_drift_score = round(float(np.mean(list(feature_scores.values()))), 4)

    # prediction drift: compare predicted positive rate if predictions available
    prediction_drift_score = 0.0
    if "prediction" in current_df.columns and "prediction" in reference_df.columns:
        ref_rate = reference_df["prediction"].mean()
        cur_rate = current_df["prediction"].mean()
        prediction_drift_score = round(float(abs(cur_rate - ref_rate)), 4)

    drift_ratio = len(drifted_features) / len(FEATURE_COLUMNS)
    drift_detected = drift_ratio > 0 and data_drift_score > DRIFT_THRESHOLD
    retrain_recommended = drift_ratio >= DRIFT_RATIO_TRIGGER or prediction_drift_score > 0.15

    return {
        "feature_scores": feature_scores,
        "drifted_features": drifted_features,
        "data_drift_score": data_drift_score,
        "prediction_drift_score": prediction_drift_score,
        "drift_detected": bool(drift_detected),
        "retrain_recommended": bool(retrain_recommended),
    }
