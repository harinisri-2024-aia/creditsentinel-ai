import json
import datetime
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List

from app.database import (
    get_db, ModelVersion, FairnessAudit, DriftReport, User, AuditLog,
    MonitoringSchedule, DriftAlert,
)
from app.utils.auth import get_current_user, can_view_fairness_reports
from app.services import fairness_service, drift_service, governance_service, ml_service, threshold_service, scheduler_service

router = APIRouter(prefix="/api/governance", tags=["governance"])


class DriftSimulationRequest(BaseModel):
    model_id: int
    drift_intensity: float = 0.0  # 0.0 = no drift, 1.0 = severe drift


class ScheduleRequest(BaseModel):
    model_id: int
    frequency: str = "off"  # off, daily, weekly
    drift_intensity: float = 0.2


def _get_owned_model_or_404(db: Session, model_id: int, current_user: User) -> ModelVersion:
    query = db.query(ModelVersion).filter(ModelVersion.id == model_id)
    if current_user.role not in ("admin", "auditor"):
        query = query.filter(ModelVersion.created_by == current_user.id)
    model_version = query.first()
    if not model_version:
        raise HTTPException(status_code=404, detail="Model not found")
    return model_version


def _load_eval_df(model_version: ModelVersion) -> pd.DataFrame:
    if not model_version.artifact_path:
        raise HTTPException(status_code=400, detail="Model has no stored evaluation data")
    eval_path = model_version.artifact_path.replace(".joblib", "_eval.pkl")
    try:
        return pd.read_pickle(eval_path)
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail="Evaluation dataset not found for this model")


@router.post("/fairness/{model_id}")
def run_fairness(model_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    model_version = _get_owned_model_or_404(db, model_id, current_user)
    eval_df = _load_eval_df(model_version)

    thresholds = threshold_service.get_thresholds_for_user(db, model_version.created_by)
    results, overall_passed = fairness_service.run_fairness_audit(eval_df, thresholds=thresholds)

    # clear old audits for this model, store fresh
    db.query(FairnessAudit).filter(FairnessAudit.model_id == model_id).delete()
    for r in results:
        db.add(FairnessAudit(
            model_id=model_id,
            user_id=model_version.created_by,
            attribute=r["attribute"],
            group_metrics=json.dumps(r["group_metrics"]),
            disparate_impact=r["disparate_impact"],
            equal_opportunity_diff=r["equal_opportunity_diff"],
            passed=r["passed"],
        ))

    model_version.fairness_status = "passed" if overall_passed else "failed"
    db.commit()

    db.add(AuditLog(
        user_id=current_user.id,
        action="fairness_audit",
        details=f"Model {model_id} fairness audit: {'PASSED' if overall_passed else 'FAILED'}",
    ))
    db.commit()

    mitigation_suggestions = []
    if not overall_passed:
        failed_results = [r for r in results if not r["passed"]]
        mitigation_suggestions = fairness_service.generate_mitigation_suggestions(failed_results)

    return {"results": results, "overall_passed": overall_passed, "mitigation_suggestions": mitigation_suggestions}


@router.get("/fairness/{model_id}")
def get_fairness(model_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _get_owned_model_or_404(db, model_id, current_user)  # ownership check
    audits = db.query(FairnessAudit).filter(FairnessAudit.model_id == model_id).all()

    results = [
        {
            "attribute": a.attribute,
            "group_metrics": json.loads(a.group_metrics),
            "disparate_impact": a.disparate_impact,
            "equal_opportunity_diff": a.equal_opportunity_diff,
            "passed": a.passed,
        }
        for a in audits
    ]
    failed_results = [r for r in results if not r["passed"]]
    mitigation_suggestions = fairness_service.generate_mitigation_suggestions(failed_results) if failed_results else []
    return {"results": results, "mitigation_suggestions": mitigation_suggestions}


@router.post("/drift")
def run_drift(payload: DriftSimulationRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    model_version = _get_owned_model_or_404(db, payload.model_id, current_user)

    reference_df = _load_eval_df(model_version)
    current_df = drift_service.simulate_production_batch(drift_intensity=payload.drift_intensity)

    # score current batch with the trained model so we can compute prediction drift
    bundle = ml_service.load_artifact(model_version.artifact_path)
    model, scaler, features = bundle["model"], bundle["scaler"], bundle["features"]
    current_df["prediction"] = model.predict(scaler.transform(current_df[features]))

    result = drift_service.run_drift_detection(reference_df, current_df)

    report = DriftReport(
        model_id=payload.model_id,
        user_id=model_version.created_by,
        data_drift_score=result["data_drift_score"],
        prediction_drift_score=result["prediction_drift_score"],
        drifted_features=json.dumps(result["drifted_features"]),
        drift_detected=result["drift_detected"],
        retrain_recommended=result["retrain_recommended"],
    )
    db.add(report)
    db.commit()
    db.refresh(report)

    if result["drift_detected"] or result["retrain_recommended"]:
        severity = "critical" if result["retrain_recommended"] else "warning"
        db.add(DriftAlert(
            model_id=payload.model_id,
            user_id=model_version.created_by,
            drift_report_id=report.id,
            severity=severity,
            message=f"Manual drift check on model {payload.model_id} flagged drift "
                     f"(data_drift={result['data_drift_score']}, prediction_drift={result['prediction_drift_score']}).",
        ))
        report.alert_sent = True
        db.commit()

    db.add(AuditLog(
        user_id=current_user.id,
        action="drift_check",
        details=f"Model {payload.model_id} drift check. Detected: {result['drift_detected']}, Retrain: {result['retrain_recommended']}",
    ))
    db.commit()

    return result


@router.get("/drift/{model_id}")
def get_drift_history(model_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _get_owned_model_or_404(db, model_id, current_user)
    reports = db.query(DriftReport).filter(DriftReport.model_id == model_id).order_by(DriftReport.created_at.desc()).all()
    return [
        {
            "id": r.id,
            "data_drift_score": r.data_drift_score,
            "prediction_drift_score": r.prediction_drift_score,
            "drifted_features": json.loads(r.drifted_features),
            "drift_detected": r.drift_detected,
            "retrain_recommended": r.retrain_recommended,
            "alert_sent": r.alert_sent,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in reports
    ]


@router.get("/alerts")
def list_alerts(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """All drift alerts for the current user's models (or all, for admin/auditor)."""
    query = db.query(DriftAlert)
    if current_user.role not in ("admin", "auditor"):
        query = query.filter(DriftAlert.user_id == current_user.id)
    alerts = query.order_by(DriftAlert.created_at.desc()).limit(100).all()
    return [
        {
            "id": a.id,
            "model_id": a.model_id,
            "severity": a.severity,
            "message": a.message,
            "acknowledged": a.acknowledged,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in alerts
    ]


@router.post("/alerts/{alert_id}/acknowledge")
def acknowledge_alert(alert_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(DriftAlert).filter(DriftAlert.id == alert_id)
    if current_user.role not in ("admin", "auditor"):
        query = query.filter(DriftAlert.user_id == current_user.id)
    alert = query.first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.acknowledged = True
    db.commit()
    return {"id": alert.id, "acknowledged": True}


@router.post("/schedule")
def set_monitoring_schedule(payload: ScheduleRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Configure automated drift monitoring (Feature 8): off, daily, or weekly."""
    if payload.frequency not in ("off", "daily", "weekly"):
        raise HTTPException(status_code=400, detail="frequency must be 'off', 'daily', or 'weekly'")

    model_version = _get_owned_model_or_404(db, payload.model_id, current_user)

    schedule = db.query(MonitoringSchedule).filter(MonitoringSchedule.model_id == payload.model_id).first()
    is_active = payload.frequency != "off"
    next_run = scheduler_service.compute_next_run(payload.frequency) if is_active else None

    if schedule:
        schedule.frequency = payload.frequency
        schedule.drift_intensity = payload.drift_intensity
        schedule.active = is_active
        schedule.next_run_at = next_run
    else:
        schedule = MonitoringSchedule(
            model_id=payload.model_id,
            user_id=model_version.created_by,
            frequency=payload.frequency,
            drift_intensity=payload.drift_intensity,
            active=is_active,
            next_run_at=next_run,
        )
        db.add(schedule)
    db.commit()
    db.refresh(schedule)

    db.add(AuditLog(
        user_id=current_user.id,
        action="monitoring_schedule_updated",
        details=f"Model {payload.model_id} drift monitoring set to '{payload.frequency}'.",
    ))
    db.commit()

    return {
        "model_id": schedule.model_id,
        "frequency": schedule.frequency,
        "drift_intensity": schedule.drift_intensity,
        "active": schedule.active,
        "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
    }


@router.get("/schedule/{model_id}")
def get_monitoring_schedule(model_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _get_owned_model_or_404(db, model_id, current_user)
    schedule = db.query(MonitoringSchedule).filter(MonitoringSchedule.model_id == model_id).first()
    if not schedule:
        return {"model_id": model_id, "frequency": "off", "drift_intensity": 0.2, "active": False, "next_run_at": None}
    return {
        "model_id": schedule.model_id,
        "frequency": schedule.frequency,
        "drift_intensity": schedule.drift_intensity,
        "active": schedule.active,
        "last_run_at": schedule.last_run_at.isoformat() if schedule.last_run_at else None,
        "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
    }


@router.post("/decide/{model_id}")
def governance_decide(model_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    model_version = _get_owned_model_or_404(db, model_id, current_user)

    metrics = {
        "accuracy": model_version.accuracy,
        "precision": model_version.precision_score,
        "recall": model_version.recall_score,
        "f1": model_version.f1,
    }
    performance_gate = governance_service.evaluate_performance_gate(metrics)
    fairness_passed = model_version.fairness_status == "passed"

    decision = governance_service.make_governance_decision(performance_gate, fairness_passed)

    model_version.governance_decision = decision["decision"]
    model_version.status = "production" if decision["decision"] == "approved" else "rejected"
    db.commit()

    db.add(AuditLog(
        user_id=current_user.id,
        action="governance_decision",
        details=f"Model {model_id}: {decision['decision'].upper()} - {decision['reason']}",
    ))
    db.commit()

    return {"performance_gate": performance_gate, **decision, "status": model_version.status}


@router.get("/audit-logs")
def audit_logs(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Audit logs scoped to the current user — UNLESS the user is an Admin or
    Auditor, who can see the full platform-wide audit trail for compliance
    purposes. This closes the same cross-user visibility gap as the model
    listing endpoint.
    """
    query = db.query(AuditLog)
    if current_user.role not in ("admin", "auditor"):
        query = query.filter(AuditLog.user_id == current_user.id)
    logs = query.order_by(AuditLog.created_at.desc()).limit(200).all()
    return [
        {
            "id": l.id,
            "user_id": l.user_id,
            "action": l.action,
            "details": l.details,
            "created_at": l.created_at.isoformat() if l.created_at else None,
        }
        for l in logs
    ]


@router.get("/compare")
def compare_models(model_ids: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Model Comparison Feature (Feature 2). Pass model_ids as a comma-separated
    list, e.g. /api/governance/compare?model_ids=1,2
    Returns per-model metrics plus pairwise diffs against the first model in
    the list (treated as the baseline) so the frontend can render deltas.
    """
    try:
        ids = [int(x) for x in model_ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(status_code=400, detail="model_ids must be a comma-separated list of integers")
    if len(ids) < 2:
        raise HTTPException(status_code=400, detail="Provide at least two model_ids to compare")

    models = [_get_owned_model_or_404(db, mid, current_user) for mid in ids]

    rows = []
    for m in models:
        latest_drift = (
            db.query(DriftReport)
            .filter(DriftReport.model_id == m.id)
            .order_by(DriftReport.created_at.desc())
            .first()
        )
        rows.append({
            "id": m.id,
            "name": m.name,
            "version": m.version,
            "algorithm": m.algorithm,
            "accuracy": m.accuracy,
            "precision": m.precision_score,
            "recall": m.recall_score,
            "f1": m.f1,
            "fairness_status": m.fairness_status,
            "governance_decision": m.governance_decision,
            "status": m.status,
            "latest_data_drift_score": latest_drift.data_drift_score if latest_drift else None,
            "latest_prediction_drift_score": latest_drift.prediction_drift_score if latest_drift else None,
        })

    baseline = rows[0]
    diffs = []
    for r in rows[1:]:
        diffs.append({
            "compared_to": baseline["id"],
            "model_id": r["id"],
            "accuracy_diff": round(r["accuracy"] - baseline["accuracy"], 4),
            "f1_diff": round(r["f1"] - baseline["f1"], 4),
            "fairness_changed": r["fairness_status"] != baseline["fairness_status"],
            "drift_diff": (
                round(r["latest_data_drift_score"] - baseline["latest_data_drift_score"], 4)
                if r["latest_data_drift_score"] is not None and baseline["latest_data_drift_score"] is not None
                else None
            ),
            "deployment_decision_changed": r["governance_decision"] != baseline["governance_decision"],
        })

    return {"models": rows, "diffs": diffs}
