import os
import json
import pandas as pd
from sqlalchemy.orm import Session

from app.database import Dataset
from app.services import ml_service

DATASET_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "datasets")
os.makedirs(DATASET_DIR, exist_ok=True)


def save_uploaded_file(user_id: int, filename: str, raw_bytes: bytes) -> str:
    safe_name = filename.replace("/", "_").replace("\\", "_")
    path = os.path.join(DATASET_DIR, f"user_{user_id}_{safe_name}")
    with open(path, "wb") as f:
        f.write(raw_bytes)
    return path


def load_dataframe(path: str) -> pd.DataFrame:
    if path.endswith(".xlsx") or path.endswith(".xls"):
        return pd.read_excel(path)
    return pd.read_csv(path)


def register_dataset(db: Session, user_id: int, filename: str, raw_bytes: bytes) -> Dataset:
    """
    Step 1-2 of the pipeline: Upload Dataset -> Validate columns.
    Persists the file to disk, attempts to parse it, validates the schema
    CreditSentinel's training pipeline requires, and stores a Dataset record
    reflecting the outcome either way (so invalid uploads are visible in the
    UI with a clear error rather than silently disappearing).
    """
    storage_path = save_uploaded_file(user_id, filename, raw_bytes)

    try:
        df = load_dataframe(storage_path)
    except Exception as e:
        dataset = Dataset(
            user_id=user_id,
            filename=filename,
            storage_path=storage_path,
            row_count=0,
            columns=json.dumps([]),
            validation_status="invalid",
            validation_message=f"Could not parse file: {e}",
        )
        db.add(dataset)
        db.commit()
        db.refresh(dataset)
        return dataset

    is_valid, message = ml_service.validate_uploaded_dataset(df)

    dataset = Dataset(
        user_id=user_id,
        filename=filename,
        storage_path=storage_path,
        row_count=len(df),
        columns=json.dumps(list(df.columns)),
        validation_status="valid" if is_valid else "invalid",
        validation_message=message,
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return dataset


def get_dataframe_for_dataset(dataset: Dataset) -> pd.DataFrame:
    return load_dataframe(dataset.storage_path)
