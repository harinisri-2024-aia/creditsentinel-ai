"""
Automated drift monitoring scheduler.

This runs as a lightweight in-process background loop started from
app/main.py on FastAPI startup (no external task queue / cron dependency
required, keeping the existing single-process deployment model intact).

Every CHECK_INTERVAL_SECONDS, it looks for MonitoringSchedule rows whose
next_run_at has passed, runs a drift check for that model using the
configured drift_intensity, persists a DriftReport, raises a DriftAlert if
the result exceeds the alert threshold, and reschedules next_run_at based on
the configured frequency (daily/weekly).
"""
import asyncio
import datetime
import json
import logging

from sqlalchemy.orm import Session

from app.database import SessionLocal, MonitoringSchedule, DriftReport, DriftAlert, ModelVersion, AuditLog
from app.services import drift_service, ml_service

logger = logging.getLogger("creditsentinel.scheduler")

CHECK_INTERVAL_SECONDS = 60  # how often the background loop wakes up to check schedules
FREQUENCY_DELTAS = {
    "daily": datetime.timedelta(days=1),
    "weekly": datetime.timedelta(weeks=1),
}


def compute_next_run(frequency: str, base: datetime.datetime = None) -> datetime.datetime:
    base = base or datetime.datetime.utcnow()
    delta = FREQUENCY_DELTAS.get(frequency)
    if not delta:
        return None
    return base + delta


def run_due_schedules_once(db: Session):
    """Runs every MonitoringSchedule whose next_run_at has passed. Returns count run."""
    now = datetime.datetime.utcnow()
    due = (
        db.query(MonitoringSchedule)
        .filter(MonitoringSchedule.active == True)  # noqa: E712
        .filter(MonitoringSchedule.frequency.in_(["daily", "weekly"]))
        .filter((MonitoringSchedule.next_run_at == None) | (MonitoringSchedule.next_run_at <= now))  # noqa: E711
        .all()
    )

    ran = 0
    for schedule in due:
        try:
            _run_single_schedule(db, schedule, now)
            ran += 1
        except Exception:
            logger.exception("Automated drift check failed for model_id=%s", schedule.model_id)
    return ran


def _run_single_schedule(db: Session, schedule: MonitoringSchedule, now: datetime.datetime):
    model_version = db.query(ModelVersion).filter(ModelVersion.id == schedule.model_id).first()
    if not model_version or not model_version.artifact_path:
        return

    eval_path = model_version.artifact_path.replace(".joblib", "_eval.pkl")
    try:
        import pandas as pd
        reference_df = pd.read_pickle(eval_path)
    except FileNotFoundError:
        return

    current_df = drift_service.simulate_production_batch(drift_intensity=schedule.drift_intensity)
    bundle = ml_service.load_artifact(model_version.artifact_path)
    model, scaler, features = bundle["model"], bundle["scaler"], bundle["features"]
    current_df["prediction"] = model.predict(scaler.transform(current_df[features]))

    result = drift_service.run_drift_detection(reference_df, current_df)

    report = DriftReport(
        model_id=schedule.model_id,
        user_id=schedule.user_id,
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
        message = (
            f"Scheduled {schedule.frequency} drift check on model {schedule.model_id} "
            f"detected drift (data_drift={result['data_drift_score']}, "
            f"prediction_drift={result['prediction_drift_score']})."
        )
        db.add(DriftAlert(
            model_id=schedule.model_id,
            user_id=schedule.user_id,
            drift_report_id=report.id,
            severity=severity,
            message=message,
        ))
        report.alert_sent = True
        db.add(AuditLog(
            user_id=schedule.user_id,
            action="drift_alert",
            details=message,
        ))
        db.commit()

    schedule.last_run_at = now
    schedule.next_run_at = compute_next_run(schedule.frequency, now)
    db.commit()


async def scheduler_loop():
    """Background asyncio loop started on FastAPI startup."""
    while True:
        try:
            db = SessionLocal()
            try:
                run_due_schedules_once(db)
            finally:
                db.close()
        except Exception:
            logger.exception("Scheduler loop iteration failed")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
