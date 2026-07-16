import os
import json
import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./creditsentinel.db")

engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {}
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Valid application roles. Stored as a plain string column for SQLite simplicity,
# validated at the API layer (see utils/auth.py::require_role).
USER_ROLES = ["admin", "data_scientist", "auditor", "loan_officer"]


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    company = Column(String, default="")
    hashed_password = Column(String, nullable=False)
    role = Column(String, default="data_scientist")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    version = Column(String, nullable=False)
    algorithm = Column(String, default="xgboost")
    params = Column(Text, default="{}")
    accuracy = Column(Float, default=0.0)
    precision_score = Column(Float, default=0.0)
    recall_score = Column(Float, default=0.0)
    f1 = Column(Float, default=0.0)
    status = Column(String, default="training")  # training, evaluated, approved, rejected, production
    governance_decision = Column(String, default="pending")
    fairness_status = Column(String, default="pending")
    artifact_path = Column(String, default="")
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=True)
    # MLflow experiment tracking run id for this training run (additive —
    # null for any model trained before MLflow integration was added, or if
    # MLflow logging wasn't available at training time).
    mlflow_run_id = Column(String, nullable=True)
    # Ownership: every model belongs to exactly one user. All list/detail queries
    # MUST filter on this column (see api/model_routes.py) so users only ever see
    # their own models, predictions, audits, and drift history.
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class FairnessAudit(Base):
    __tablename__ = "fairness_audits"

    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(Integer, ForeignKey("model_versions.id"))
    # Denormalized owner copy so fairness queries don't need a join to scope by user.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    attribute = Column(String, nullable=False)  # gender, age_group, region
    group_metrics = Column(Text, default="{}")
    disparate_impact = Column(Float, default=1.0)
    equal_opportunity_diff = Column(Float, default=0.0)
    passed = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class DriftReport(Base):
    __tablename__ = "drift_reports"

    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(Integer, ForeignKey("model_versions.id"))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    data_drift_score = Column(Float, default=0.0)
    prediction_drift_score = Column(Float, default=0.0)
    drifted_features = Column(Text, default="[]")
    drift_detected = Column(Boolean, default=False)
    retrain_recommended = Column(Boolean, default=False)
    alert_sent = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)
    details = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Prediction(Base):
    __tablename__ = "predictions"

    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(Integer, ForeignKey("model_versions.id"))
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    applicant_name = Column(String, default="Unnamed Applicant")
    input_payload = Column(Text, default="{}")
    risk_score = Column(Float, default=0.0)
    decision = Column(String, default="")
    explanation = Column(Text, default="{}")
    model_version_label = Column(String, default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String, nullable=False)
    storage_path = Column(String, nullable=False)
    row_count = Column(Integer, default=0)
    columns = Column(Text, default="[]")
    validation_status = Column(String, default="pending")  # pending, valid, invalid
    validation_message = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class FairnessThreshold(Base):
    """
    Per-user configurable fairness gate thresholds. Falls back to the global
    defaults in services/fairness_service.py when a user has no row yet.
    Only Admins may write to this table (enforced in api/admin_routes.py).
    """
    __tablename__ = "fairness_thresholds"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, unique=True)
    disparate_impact_min = Column(Float, default=0.8)
    equal_opportunity_max = Column(Float, default=0.1)
    updated_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow)


class MonitoringSchedule(Base):
    """Per-model automated drift monitoring schedule."""
    __tablename__ = "monitoring_schedules"

    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(Integer, ForeignKey("model_versions.id"), nullable=False, unique=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    frequency = Column(String, default="off")  # off, daily, weekly
    drift_intensity = Column(Float, default=0.2)
    last_run_at = Column(DateTime, nullable=True)
    next_run_at = Column(DateTime, nullable=True)
    active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class DriftAlert(Base):
    """Alerts generated when an automated or manual drift run exceeds threshold."""
    __tablename__ = "drift_alerts"

    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(Integer, ForeignKey("model_versions.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    drift_report_id = Column(Integer, ForeignKey("drift_reports.id"), nullable=False)
    severity = Column(String, default="warning")  # warning, critical
    message = Column(Text, default="")
    acknowledged = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class RetrainingTriggerEvaluation(Base):
    """
    Stores the result of evaluating the automated retraining trigger rules
    (data drift / performance / fairness) for a model at a point in time.
    Purely additive: a new table, doesn't touch any existing table or
    governance/drift logic — it reads the same drift/fairness/performance
    numbers those features already compute and applies the trigger
    thresholds from this feature on top.
    """
    __tablename__ = "retraining_trigger_evaluations"

    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(Integer, ForeignKey("model_versions.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    triggers = Column(Text, default="[]")  # JSON list of per-rule evaluation results
    any_triggered = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    _run_light_migrations()


def _run_light_migrations():
    """
    SQLite doesn't always pick up new nullable columns added to existing models
    cleanly when create_all() runs against a pre-existing DB file from an older
    version of the app. This adds any missing columns so upgrades from the
    previous CreditSentinel schema don't crash on startup.
    """
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    migrations = {
        "predictions": [
            ("user_id", "INTEGER"),
            ("applicant_name", "TEXT DEFAULT 'Unnamed Applicant'"),
            ("model_version_label", "TEXT DEFAULT ''"),
        ],
        "fairness_audits": [("user_id", "INTEGER")],
        "drift_reports": [("user_id", "INTEGER"), ("alert_sent", "BOOLEAN DEFAULT 0")],
        "model_versions": [("dataset_id", "INTEGER"), ("mlflow_run_id", "TEXT")],
    }

    with engine.connect() as conn:
        for table, cols in migrations.items():
            if table not in existing_tables:
                continue
            existing_cols = {c["name"] for c in inspector.get_columns(table)}
            for col_name, col_type in cols:
                if col_name not in existing_cols:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}"))
        conn.commit()

        # Backfill user_id on legacy rows by joining through model_versions.created_by
        # so data created before this migration isn't orphaned/invisible.
        if "predictions" in existing_tables:
            conn.execute(text(
                "UPDATE predictions SET user_id = ("
                "  SELECT created_by FROM model_versions WHERE model_versions.id = predictions.model_id"
                ") WHERE user_id IS NULL"
            ))
        if "fairness_audits" in existing_tables:
            conn.execute(text(
                "UPDATE fairness_audits SET user_id = ("
                "  SELECT created_by FROM model_versions WHERE model_versions.id = fairness_audits.model_id"
                ") WHERE user_id IS NULL"
            ))
        if "drift_reports" in existing_tables:
            conn.execute(text(
                "UPDATE drift_reports SET user_id = ("
                "  SELECT created_by FROM model_versions WHERE model_versions.id = drift_reports.model_id"
                ") WHERE user_id IS NULL"
            ))
        conn.commit()
