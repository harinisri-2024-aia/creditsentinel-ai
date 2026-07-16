from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db, ModelVersion, FairnessAudit, DriftReport, AuditLog, User
from app.utils.auth import get_current_user
from app.utils import report as report_utils
from app.services import threshold_service

router = APIRouter(prefix="/api/reports", tags=["reports"])


def _get_owned_model_or_404(db: Session, model_id: int, current_user: User) -> ModelVersion:
    query = db.query(ModelVersion).filter(ModelVersion.id == model_id)
    if current_user.role not in ("admin", "auditor"):
        query = query.filter(ModelVersion.created_by == current_user.id)
    model_version = query.first()
    if not model_version:
        raise HTTPException(status_code=404, detail="Model not found")
    return model_version


def _build_context(db: Session, model_version: ModelVersion):
    fairness_audits = (
        db.query(FairnessAudit).filter(FairnessAudit.model_id == model_version.id).all()
    )
    drift_reports = (
        db.query(DriftReport)
        .filter(DriftReport.model_id == model_version.id)
        .order_by(DriftReport.created_at.desc())
        .all()
    )
    governance_logs = (
        db.query(AuditLog)
        .filter(AuditLog.details.like(f"Model {model_version.id}%") | AuditLog.details.like(f"%model {model_version.id}%"))
        .order_by(AuditLog.created_at.desc())
        .all()
    )
    thresholds = threshold_service.get_thresholds_for_user(db, model_version.created_by)
    return report_utils.build_report_context(model_version, fairness_audits, drift_reports, governance_logs, thresholds)


@router.get("/{model_id}/export")
def export_report(
    model_id: int,
    format: str = Query("pdf", pattern="^(pdf|csv)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Compliance Report Export (Feature 9). format=pdf or format=csv."""
    model_version = _get_owned_model_or_404(db, model_id, current_user)
    context = _build_context(db, model_version)

    safe_name = f"{model_version.name}_{model_version.version}".replace(" ", "_")

    if format == "csv":
        content = report_utils.build_csv_report(context)
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename={safe_name}_compliance_report.csv"},
        )

    content = report_utils.build_pdf_report(context)
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={safe_name}_compliance_report.pdf"},
    )
