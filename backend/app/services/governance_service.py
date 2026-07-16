PERFORMANCE_THRESHOLDS = {
    "accuracy_min": 0.70,
    "f1_min": 0.60,
}


def evaluate_performance_gate(metrics: dict) -> dict:
    passed = (
        metrics.get("accuracy", 0) >= PERFORMANCE_THRESHOLDS["accuracy_min"]
        and metrics.get("f1", 0) >= PERFORMANCE_THRESHOLDS["f1_min"]
    )
    return {
        "passed": bool(passed),
        "thresholds": PERFORMANCE_THRESHOLDS,
        "metrics": metrics,
    }


def make_governance_decision(performance_gate: dict, fairness_passed: bool) -> dict:
    """
    A model can move to production only if performance passes AND fairness passes.
    """
    performance_passed = performance_gate["passed"]

    if performance_passed and fairness_passed:
        decision = "approved"
        reason = "Model passed both performance and fairness gates."
    elif not performance_passed and not fairness_passed:
        decision = "rejected"
        reason = "Model failed both performance and fairness gates."
    elif not performance_passed:
        decision = "rejected"
        reason = "Model failed the performance gate (accuracy/F1 below threshold)."
    else:
        decision = "rejected"
        reason = "Model failed the fairness gate (disparate impact or equal opportunity violation)."

    return {
        "decision": decision,
        "reason": reason,
        "performance_passed": performance_passed,
        "fairness_passed": fairness_passed,
    }
