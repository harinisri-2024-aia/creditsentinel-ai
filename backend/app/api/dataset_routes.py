import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

from app.database import get_db, Dataset, AuditLog, User
from app.utils.auth import get_current_user, can_upload_datasets
from app.services import dataset_service

router = APIRouter(prefix="/api/datasets", tags=["datasets"])

ALLOWED_EXTENSIONS = (".csv", ".xlsx", ".xls")


@router.post("/upload")
async def upload_dataset(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(can_upload_datasets),
):
    """
    Step 1 of the pipeline: Upload Dataset -> Validate columns.
    Accepts a CSV/XLSX file, validates it against the schema the training
    pipeline requires (see ml_service.validate_uploaded_dataset), and stores
    the result either way so failures are visible rather than silent.
    """
    if not file.filename.lower().endswith(ALLOWED_EXTENSIONS):
        raise HTTPException(status_code=400, detail=f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

    raw_bytes = await file.read()
    if len(raw_bytes) == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(raw_bytes) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 25MB)")

    dataset = dataset_service.register_dataset(db, current_user.id, file.filename, raw_bytes)

    db.add(AuditLog(
        user_id=current_user.id,
        action="dataset_uploaded",
        details=f"Uploaded dataset '{file.filename}' ({dataset.row_count} rows): {dataset.validation_status} — {dataset.validation_message}",
    ))
    db.commit()

    return {
        "id": dataset.id,
        "filename": dataset.filename,
        "row_count": dataset.row_count,
        "columns": json.loads(dataset.columns or "[]"),
        "validation_status": dataset.validation_status,
        "validation_message": dataset.validation_message,
    }


@router.get("")
def list_datasets(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    datasets = (
        db.query(Dataset)
        .filter(Dataset.user_id == current_user.id)
        .order_by(Dataset.created_at.desc())
        .all()
    )
    return [
        {
            "id": d.id,
            "filename": d.filename,
            "row_count": d.row_count,
            "columns": json.loads(d.columns or "[]"),
            "validation_status": d.validation_status,
            "validation_message": d.validation_message,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in datasets
    ]


@router.get("/required-schema")
def required_schema():
    """Tells the frontend exactly which columns an uploaded file must contain."""
    from app.services.ml_service import FEATURE_COLUMNS, SENSITIVE_COLUMNS, TARGET_COLUMN
    return {
        "feature_columns": FEATURE_COLUMNS,
        "sensitive_columns": SENSITIVE_COLUMNS,
        "target_column": TARGET_COLUMN,
        "notes": "Target column must be binary (0 = no default, 1 = default). Minimum 50 rows.",
    }


@router.delete("/{dataset_id}")
def delete_dataset(dataset_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id, Dataset.user_id == current_user.id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    db.delete(dataset)
    db.commit()
    return {"deleted": True}
