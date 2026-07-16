import pandas as pd
import numpy as np

# Global fallback defaults. A user/admin can override these per-account via
# the FairnessThreshold table (see services/threshold_service.py); these
# constants are only used when no override row exists yet.
DEFAULT_FAIRNESS_THRESHOLDS = {
    "disparate_impact_min": 0.8,   # 80% rule
    "equal_opportunity_max": 0.1,  # max allowed gap
}


def _group_metrics(df: pd.DataFrame, attribute: str):
    """Compute approval rate and true positive rate per group."""
    groups = {}
    for group_value, sub in df.groupby(attribute):
        total = len(sub)
        approvals = (sub["prediction"] == 0).sum()  # 0 = approve (no default predicted)
        approval_rate = approvals / total if total else 0.0

        positives = sub[sub["default"] == 1]
        tpr = (positives["prediction"] == 1).mean() if len(positives) else 0.0

        groups[str(group_value)] = {
            "count": int(total),
            "approval_rate": round(float(approval_rate), 4),
            "true_positive_rate": round(float(tpr), 4),
        }
    return groups


def audit_attribute(df: pd.DataFrame, attribute: str, thresholds: dict = None):
    thresholds = thresholds or DEFAULT_FAIRNESS_THRESHOLDS
    group_metrics = _group_metrics(df, attribute)
    approval_rates = [g["approval_rate"] for g in group_metrics.values()]
    tprs = [g["true_positive_rate"] for g in group_metrics.values()]

    disparate_impact = (min(approval_rates) / max(approval_rates)) if max(approval_rates) > 0 else 1.0
    equal_opportunity_diff = (max(tprs) - min(tprs)) if tprs else 0.0

    passed = (
        disparate_impact >= thresholds["disparate_impact_min"]
        and equal_opportunity_diff <= thresholds["equal_opportunity_max"]
    )

    # Identify which specific groups are driving a failure, used both for
    # display and to power the bias-mitigation suggestions below.
    worst_group = min(group_metrics.items(), key=lambda kv: kv[1]["approval_rate"])[0] if group_metrics else None
    best_group = max(group_metrics.items(), key=lambda kv: kv[1]["approval_rate"])[0] if group_metrics else None

    return {
        "attribute": attribute,
        "group_metrics": group_metrics,
        "disparate_impact": round(float(disparate_impact), 4),
        "equal_opportunity_diff": round(float(equal_opportunity_diff), 4),
        "passed": bool(passed),
        "thresholds_used": thresholds,
        "lowest_approval_group": worst_group,
        "highest_approval_group": best_group,
    }


def run_fairness_audit(eval_df: pd.DataFrame, attributes=None, thresholds: dict = None):
    attributes = attributes or ["gender", "age_group", "region"]
    results = [audit_attribute(eval_df, attr, thresholds) for attr in attributes]
    overall_passed = all(r["passed"] for r in results)
    return results, overall_passed


def generate_mitigation_suggestions(failed_results: list, model_metrics: dict = None):
    """
    Produces concrete, actionable bias-mitigation suggestions for each failed
    fairness attribute, rather than just rejecting the model outright.

    Each suggestion includes a `type` so the frontend can render an icon/CTA,
    and a one-line `action` plus a slightly longer `rationale`.
    """
    suggestions = []

    for r in failed_results:
        attr = r["attribute"]
        worst = r.get("lowest_approval_group")
        best = r.get("highest_approval_group")

        if r["disparate_impact"] < DEFAULT_FAIRNESS_THRESHOLDS["disparate_impact_min"]:
            suggestions.append({
                "attribute": attr,
                "type": "remove_feature",
                "action": f"Remove or de-weight features correlated with '{attr}'",
                "rationale": (
                    f"The disparate impact ratio for {attr} is {r['disparate_impact']} "
                    f"(below the {DEFAULT_FAIRNESS_THRESHOLDS['disparate_impact_min']} minimum). "
                    f"Group '{worst}' is approved far less often than group '{best}'. "
                    "A proxy feature may be encoding this attribute indirectly."
                ),
            })
            suggestions.append({
                "attribute": attr,
                "type": "rebalance_dataset",
                "action": f"Rebalance training data across {attr} groups",
                "rationale": (
                    f"If group '{worst}' is underrepresented or has a skewed default rate in the "
                    "training set, the model may have learned a biased decision boundary. "
                    "Resampling or reweighting examples can reduce this gap."
                ),
            })

        if r["equal_opportunity_diff"] > DEFAULT_FAIRNESS_THRESHOLDS["equal_opportunity_max"]:
            suggestions.append({
                "attribute": attr,
                "type": "adjust_threshold",
                "action": f"Apply a per-group decision threshold for {attr}",
                "rationale": (
                    f"The true-positive-rate gap for {attr} is {r['equal_opportunity_diff']} "
                    f"(above the {DEFAULT_FAIRNESS_THRESHOLDS['equal_opportunity_max']} max allowed). "
                    "Calibrating a separate approval threshold per group can equalize opportunity "
                    "without retraining the underlying model."
                ),
            })

        suggestions.append({
            "attribute": attr,
            "type": "retrain_model",
            "action": "Retrain with a fairness-aware objective or constraint",
            "rationale": (
                "Techniques such as adversarial debiasing, reweighing (Kamiran & Calders), "
                "or constrained optimization (e.g. fairlearn's ExponentiatedGradient) can "
                "directly optimize for both accuracy and fairness during training."
            ),
        })

    # De-duplicate identical (attribute, type) suggestion pairs across attributes.
    seen = set()
    deduped = []
    for s in suggestions:
        key = (s["attribute"], s["type"])
        if key not in seen:
            seen.add(key)
            deduped.append(s)
    return deduped
