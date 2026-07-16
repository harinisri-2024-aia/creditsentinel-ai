"""
Automated retraining trigger rules (additive monitoring feature).

This module evaluates three independent rules against a model's most recent
drift report, fairness audit, and recorded accuracy, and recommends
retraining when any rule's condition is violated. It is purely a read-only
evaluation layer on top of data CreditSentinel's existing drift_service,
fairness_service, and ModelVersion records already produce — it does not
change how drift, fairness, or accuracy are computed, and it does not modify
the existing governance approval/rejection workflow.

Rules (exact thresholds as specified):

  1. Data Drift Trigger
     If PSI (Population Stability Index) > 0.2
     -> "Retraining recommended due to data drift"

  2. Performance Trigger
     If Accuracy < 85%
     -> "Retraining recommended due to performance degradation"

  3. Fairness Trigger
     If Disparate Impact Ratio < 0.8 OR Equal Opportunity Difference exceeds
     threshold
     -> "Retraining recommended due to fairness violation"

Note on PSI: CreditSentinel's existing drift_service computes a normalized
"data_drift_score" in the same spirit as PSI (0 = no drift, higher = more
drift) using bucketed distribution comparisons. We treat that score as the
PSI value this trigger rule is evaluated against, since CreditSentinel does
not maintain a separately-named "PSI" figure elsewhere in the app.
"""
from typing import Optional
from sqlalchemy.orm import Session

from app.database import DriftReport, FairnessAudit, ModelVersion
from app.services import threshold_service

# Exact thresholds as specified in the feature request.
PSI_THRESHOLD = 0.2
ACCURACY_THRESHOLD = 0.85
DISPARATE_IMPACT_MIN = 0.8
# Equal Opportunity Difference threshold: falls back to the same
# admin-configurable fairness threshold (services/threshold_service.py) the
# existing fairness audit already uses, so this rule stays consistent with
# whatever an admin has configured rather than introducing a second,
# disconnected threshold.
EQUAL_OPPORTUNITY_MAX_DEFAULT = 0.10


def _latest_drift_report(db: Session, model_id: int) -> Optional[DriftReport]:
    return (
        db.query(DriftReport)
        .filter(DriftReport.model_id == model_id)
        .order_by(DriftReport.created_at.desc())
        .first()
    )


def _latest_fairness_audits(db: Session, model_id: int):
    return (
        db.query(FairnessAudit)
        .filter(FairnessAudit.model_id == model_id)
        .order_by(FairnessAudit.created_at.desc())
        .all()
    )


def evaluate_triggers(db: Session, model: ModelVersion, equal_opportunity_max: float = None) -> dict:
    """
    Evaluates all three retraining trigger rules for the given model using
    its most recent drift report and fairness audits, plus its recorded
    accuracy. Returns a dict with one entry per rule plus an overall
    `any_triggered` flag, each entry containing the trigger name, whether it
    fired, the current value, the required threshold, and a human-readable
    reason matching the requested format (e.g. "PSI = 0.35 exceeded allowed
    threshold 0.2").

    If `equal_opportunity_max` isn't explicitly provided, the model owner's
    configured fairness threshold (admin-configurable, same one the existing
    fairness audit gate uses) is used instead of a hardcoded number.
    """
    if equal_opportunity_max is None:
        user_thresholds = threshold_service.get_thresholds_for_user(db, model.created_by)
        eo_threshold = user_thresholds.get("equal_opportunity_max", EQUAL_OPPORTUNITY_MAX_DEFAULT)
    else:
        eo_threshold = equal_opportunity_max
    triggers = []

    # --- 1. Data Drift Trigger (PSI > 0.2) ---------------------------------
    drift_report = _latest_drift_report(db, model.id)
    if drift_report is not None:
        psi_value = round(float(drift_report.data_drift_score), 4)
        drift_triggered = psi_value > PSI_THRESHOLD
        triggers.append({
            "trigger_name": "Data Drift Trigger",
            "metric": "PSI",
            "triggered": drift_triggered,
            "current_value": psi_value,
            "threshold": PSI_THRESHOLD,
            "comparison": "greater_than",
            "reason": (
                f"PSI = {psi_value} exceeded allowed threshold {PSI_THRESHOLD}"
                if drift_triggered
                else f"PSI = {psi_value} is within allowed threshold {PSI_THRESHOLD}"
            ),
            "recommendation": "Retraining recommended due to data drift" if drift_triggered else None,
            "data_available": True,
            "evaluated_at": drift_report.created_at.isoformat() if drift_report.created_at else None,
        })
    else:
        triggers.append({
            "trigger_name": "Data Drift Trigger",
            "metric": "PSI",
            "triggered": False,
            "current_value": None,
            "threshold": PSI_THRESHOLD,
            "comparison": "greater_than",
            "reason": "No drift report has been run yet for this model.",
            "recommendation": None,
            "data_available": False,
            "evaluated_at": None,
        })

    # --- 2. Performance Trigger (Accuracy < 85%) ---------------------------
    accuracy = float(model.accuracy or 0.0)
    perf_triggered = accuracy < ACCURACY_THRESHOLD
    accuracy_pct = round(accuracy * 100, 2)
    threshold_pct = round(ACCURACY_THRESHOLD * 100, 2)
    triggers.append({
        "trigger_name": "Performance Trigger",
        "metric": "Accuracy",
        "triggered": perf_triggered,
        "current_value": accuracy_pct,
        "threshold": threshold_pct,
        "comparison": "less_than",
        "reason": (
            f"Accuracy = {accuracy_pct}% fell below required threshold {threshold_pct}%"
            if perf_triggered
            else f"Accuracy = {accuracy_pct}% meets required threshold {threshold_pct}%"
        ),
        "recommendation": "Retraining recommended due to performance degradation" if perf_triggered else None,
        "data_available": True,
        "evaluated_at": None,
    })

    # --- 3. Fairness Trigger (DI < 0.8 OR EOD exceeds threshold) -----------
    fairness_audits = _latest_fairness_audits(db, model.id)
    if fairness_audits:
        # Use the worst (most-violating) attribute across gender/age_group/region
        # so a violation on any single protected attribute is surfaced.
        worst_di_audit = min(fairness_audits, key=lambda a: a.disparate_impact)
        worst_eod_audit = max(fairness_audits, key=lambda a: abs(a.equal_opportunity_diff))

        di_value = round(float(worst_di_audit.disparate_impact), 4)
        eod_value = round(abs(float(worst_eod_audit.equal_opportunity_diff)), 4)

        di_triggered = di_value < DISPARATE_IMPACT_MIN
        eod_triggered = eod_value > eo_threshold
        fairness_triggered = di_triggered or eod_triggered

        reasons = []
        if di_triggered:
            reasons.append(
                f"Disparate Impact Ratio = {di_value} ({worst_di_audit.attribute}) "
                f"fell below allowed threshold {DISPARATE_IMPACT_MIN}"
            )
        if eod_triggered:
            reasons.append(
                f"Equal Opportunity Difference = {eod_value} ({worst_eod_audit.attribute}) "
                f"exceeded allowed threshold {eo_threshold}"
            )
        if not reasons:
            reasons.append(
                f"Disparate Impact Ratio = {di_value} and Equal Opportunity Difference = {eod_value} "
                f"are within allowed thresholds ({DISPARATE_IMPACT_MIN} / {eo_threshold})"
            )

        triggers.append({
            "trigger_name": "Fairness Trigger",
            "metric": "Disparate Impact Ratio / Equal Opportunity Difference",
            "triggered": fairness_triggered,
            "current_value": {"disparate_impact": di_value, "equal_opportunity_diff": eod_value},
            "threshold": {"disparate_impact_min": DISPARATE_IMPACT_MIN, "equal_opportunity_max": eo_threshold},
            "comparison": "di_less_than_or_eod_greater_than",
            "reason": "; ".join(reasons),
            "recommendation": "Retraining recommended due to fairness violation" if fairness_triggered else None,
            "data_available": True,
            "evaluated_at": worst_di_audit.created_at.isoformat() if worst_di_audit.created_at else None,
        })
    else:
        triggers.append({
            "trigger_name": "Fairness Trigger",
            "metric": "Disparate Impact Ratio / Equal Opportunity Difference",
            "triggered": False,
            "current_value": None,
            "threshold": {"disparate_impact_min": DISPARATE_IMPACT_MIN, "equal_opportunity_max": eo_threshold},
            "comparison": "di_less_than_or_eod_greater_than",
            "reason": "No fairness audit has been run yet for this model.",
            "recommendation": None,
            "data_available": False,
            "evaluated_at": None,
        })

    any_triggered = any(t["triggered"] for t in triggers)
    return {
        "model_id": model.id,
        "model_name": model.name,
        "model_version": model.version,
        "triggers": triggers,
        "any_triggered": any_triggered,
    }
