import json
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db, ModelVersion, User, AuditLog, Prediction, Dataset, RetrainingTriggerEvaluation
from app.utils.auth import get_current_user, can_train_models
from app.services import ml_service, dataset_service, mlflow_service, retraining_trigger_service

router = APIRouter(prefix="/api/models", tags=["models"])


class TrainRequest(BaseModel):
    name: str = "credit-risk-model"
    algorithm: str = "xgboost"
    n_estimators: Optional[int] = 150
    max_depth: Optional[int] = 5
    learning_rate: Optional[float] = 0.1
    dataset_id: Optional[int] = None  # if set, train on this user's uploaded dataset
    # Additive: hyperparameters for the two new algorithms (Logistic
    # Regression, Decision Tree). Ignored by xgboost/random_forest training,
    # exactly like learning_rate is already ignored by random_forest today.
    C: Optional[float] = 1.0
    max_iter: Optional[int] = 1000
    solver: Optional[str] = "lbfgs"
    min_samples_leaf: Optional[int] = 5
    criterion: Optional[str] = "gini"


class PredictRequest(BaseModel):
    model_id: int
    applicant_name: Optional[str] = "Unnamed Applicant"
    age: float
    annual_income: float
    credit_score: float
    loan_amount: float
    loan_term_months: float
    existing_debt: float
    employment_years: float
    num_credit_lines: float


def _model_to_dict(m: ModelVersion) -> dict:
    return {
        "id": m.id,
        "name": m.name,
        "version": m.version,
        "algorithm": m.algorithm,
        "accuracy": m.accuracy,
        "precision": m.precision_score,
        "recall": m.recall_score,
        "f1": m.f1,
        "status": m.status,
        "governance_decision": m.governance_decision,
        "fairness_status": m.fairness_status,
        "dataset_id": m.dataset_id,
        "mlflow_run_id": m.mlflow_run_id,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _get_owned_model_or_404(db: Session, model_id: int, current_user: User) -> ModelVersion:
    """
    Ownership guard used by every endpoint that touches a specific model.

    Admins and Auditors can view any model (read-only governance/compliance
    visibility), but Data Scientists and Loan Officers may only access models
    they personally created. This is the core fix for the "Total Models"
    cross-user leakage bug: ownership is enforced once, here, instead of being
    re-implemented (and potentially forgotten) in every route.
    """
    query = db.query(ModelVersion).filter(ModelVersion.id == model_id)
    if current_user.role not in ("admin", "auditor"):
        query = query.filter(ModelVersion.created_by == current_user.id)
    model_version = query.first()
    if not model_version:
        raise HTTPException(status_code=404, detail="Model not found")
    return model_version


@router.get("")
def list_models(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Returns only the current user's models — UNLESS the user is an Admin or
    Auditor, who get full visibility across all users for governance/audit
    purposes. This is the fix for the bug where "Total Models" counted every
    user's models globally.
    """
    query = db.query(ModelVersion)
    if current_user.role not in ("admin", "auditor"):
        query = query.filter(ModelVersion.created_by == current_user.id)
    models = query.order_by(ModelVersion.created_at.desc()).all()
    return [_model_to_dict(m) for m in models]


@router.post("/train")
def train_model(
    payload: TrainRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(can_train_models),
):
    # Version numbering is scoped to THIS user's models with this name, so
    # Harini's first model is always v1.0 regardless of how many models other
    # users have trained with the same default name.
    existing_count = (
        db.query(ModelVersion)
        .filter(ModelVersion.name == payload.name, ModelVersion.created_by == current_user.id)
        .count()
    )
    version = f"v{existing_count + 1}.0"

    params = {
        "n_estimators": payload.n_estimators,
        "max_depth": payload.max_depth,
        "learning_rate": payload.learning_rate,
        "C": payload.C,
        "max_iter": payload.max_iter,
        "solver": payload.solver,
        "min_samples_leaf": payload.min_samples_leaf,
        "criterion": payload.criterion,
    }

    dataset_df = None
    dataset_id = None
    if payload.dataset_id:
        dataset = (
            db.query(Dataset)
            .filter(Dataset.id == payload.dataset_id, Dataset.user_id == current_user.id)
            .first()
        )
        if not dataset:
            raise HTTPException(status_code=404, detail="Dataset not found")
        if dataset.validation_status != "valid":
            raise HTTPException(status_code=400, detail="Dataset failed validation and cannot be used for training")
        dataset_df = dataset_service.get_dataframe_for_dataset(dataset)
        dataset_id = dataset.id

    model, scaler, algorithm, metrics, eval_df, baseline_means = ml_service.train_model(
        payload.algorithm, params, dataset_df=dataset_df
    )

    # Only the hyperparameters actually used by the chosen algorithm are
    # stored (e.g. a decision_tree run won't record an irrelevant
    # learning_rate) — this keeps params/MLflow tracking accurate per model.
    effective_params = ml_service.resolve_effective_params(algorithm, params)

    model_version = ModelVersion(
        name=payload.name,
        version=version,
        algorithm=algorithm,
        params=json.dumps(effective_params),
        accuracy=metrics["accuracy"],
        precision_score=metrics["precision"],
        recall_score=metrics["recall"],
        f1=metrics["f1"],
        status="evaluated",
        dataset_id=dataset_id,
        created_by=current_user.id,
    )
    db.add(model_version)
    db.commit()
    db.refresh(model_version)

    artifact_path = ml_service.save_artifact(model, scaler, model_version.id, baseline_means)
    model_version.artifact_path = artifact_path

    # MLflow experiment tracking (additive): logs this run's version,
    # parameters, metrics, and model artifact. Safe no-op if MLflow isn't
    # available — never blocks or fails model training.
    mlflow_run_id = mlflow_service.log_training_run(
        model=model,
        algorithm=algorithm,
        version=version,
        model_name=payload.name,
        params=effective_params,
        metrics=metrics,
        dataset_label=f"dataset_{dataset_id}" if dataset_id else "synthetic",
        model_db_id=model_version.id,
    )
    if mlflow_run_id:
        model_version.mlflow_run_id = mlflow_run_id
    db.commit()

    # cache eval dataframe to disk for fairness/drift audits
    eval_path = artifact_path.replace(".joblib", "_eval.pkl")
    eval_df.to_pickle(eval_path)

    db.add(AuditLog(
        user_id=current_user.id,
        action="model_trained",
        details=f"Trained {payload.name} {version} using {algorithm}"
                f"{' on uploaded dataset ' + str(dataset_id) if dataset_id else ' on synthetic dataset'}. "
                f"Metrics: {metrics}",
    ))
    db.commit()

    return {
        "id": model_version.id,
        "name": model_version.name,
        "version": model_version.version,
        "algorithm": model_version.algorithm,
        "params": effective_params,
        "metrics": metrics,
        "status": model_version.status,
        "mlflow_run_id": model_version.mlflow_run_id,
        "mlflow_tracking": mlflow_service.get_tracking_info(),
    }


@router.post("/predict")
def predict(
    payload: PredictRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    model_version = _get_owned_model_or_404(db, payload.model_id, current_user)
    if not model_version.artifact_path:
        raise HTTPException(status_code=404, detail="Model not found or not trained")

    input_fields = payload.model_dump(exclude={"model_id", "applicant_name"})
    result = ml_service.predict_single(model_version.artifact_path, input_fields)

    pred_record = Prediction(
        model_id=model_version.id,
        user_id=current_user.id,
        applicant_name=payload.applicant_name or "Unnamed Applicant",
        input_payload=json.dumps(input_fields),
        risk_score=result["risk_score"],
        decision=result["decision"],
        explanation=json.dumps({
            "legacy": result["explanation"],
            "shap_explanation": result["shap_explanation"],
            "shap_waterfall": result.get("shap_waterfall"),
            "counterfactuals": result["counterfactuals"],
        }),
        model_version_label=f"{model_version.name} {model_version.version}",
    )
    db.add(pred_record)
    db.commit()
    db.refresh(pred_record)

    return {**result, "application_id": pred_record.id}


@router.get("/applicants")
def list_applicants(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Applicant Management Dashboard (Feature 1): lists every prediction made
    by the current user (their "loan applications"), newest first. Admins
    and Auditors see all applicants across users for oversight.
    """
    query = db.query(Prediction)
    if current_user.role not in ("admin", "auditor"):
        query = query.filter(Prediction.user_id == current_user.id)
    predictions = query.order_by(Prediction.created_at.desc()).all()

    return [
        {
            "application_id": p.id,
            "applicant_name": p.applicant_name,
            "risk_score": p.risk_score,
            "decision": "Approved" if p.decision == "APPROVE" else "Declined",
            "model_version_used": p.model_version_label,
            "date": p.created_at.isoformat() if p.created_at else None,
        }
        for p in predictions
    ]


@router.get("/applicants/{application_id}")
def get_applicant(application_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Detail view for a single applicant: prediction, risk score, explanation, factors."""
    query = db.query(Prediction).filter(Prediction.id == application_id)
    if current_user.role not in ("admin", "auditor"):
        query = query.filter(Prediction.user_id == current_user.id)
    p = query.first()
    if not p:
        raise HTTPException(status_code=404, detail="Applicant record not found")

    explanation = json.loads(p.explanation or "{}")
    return {
        "application_id": p.id,
        "applicant_name": p.applicant_name,
        "risk_score": p.risk_score,
        "decision": "Approved" if p.decision == "APPROVE" else "Declined",
        "model_version_used": p.model_version_label,
        "date": p.created_at.isoformat() if p.created_at else None,
        "input_payload": json.loads(p.input_payload or "{}"),
        "shap_explanation": explanation.get("shap_explanation", []),
        "shap_waterfall": explanation.get("shap_waterfall"),
        "counterfactuals": explanation.get("counterfactuals", []),
        "legacy_explanation": explanation.get("legacy", []),
    }


@router.get("/{model_id}/mlflow-history")
def get_mlflow_history(model_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Additive: returns this model's MLflow experiment tracking history (every
    training run logged for this model_id — version, params, metrics,
    status). Returns an empty list (not an error) if MLflow isn't available
    or no runs have been logged yet, so the comparison/model detail UI can
    always render this section without special-casing failures.
    """
    m = _get_owned_model_or_404(db, model_id, current_user)
    history = mlflow_service.get_run_history(model_db_id=m.id)
    return {
        "model_id": m.id,
        "mlflow_tracking": mlflow_service.get_tracking_info(),
        "runs": history,
    }


@router.get("/{model_id}/retraining-triggers")
def get_retraining_triggers(model_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Additive: evaluates the automated retraining trigger rules (data drift /
    performance / fairness) for this model against its most recent drift
    report, fairness audits, and recorded accuracy, and returns whether
    retraining is recommended and why. Also persists the evaluation to
    retraining_trigger_evaluations for history, mirroring how drift reports
    are persisted.
    """
    m = _get_owned_model_or_404(db, model_id, current_user)
    result = retraining_trigger_service.evaluate_triggers(db, m)

    db.add(RetrainingTriggerEvaluation(
        model_id=m.id,
        user_id=current_user.id,
        triggers=json.dumps(result["triggers"]),
        any_triggered=result["any_triggered"],
    ))
    db.commit()

    return result


@router.get("/{model_id}")
def get_model(model_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    m = _get_owned_model_or_404(db, model_id, current_user)
    return {
        "id": m.id,
        "name": m.name,
        "version": m.version,
        "algorithm": m.algorithm,
        "params": json.loads(m.params or "{}"),
        "accuracy": m.accuracy,
        "precision": m.precision_score,
        "recall": m.recall_score,
        "f1": m.f1,
        "status": m.status,
        "governance_decision": m.governance_decision,
        "fairness_status": m.fairness_status,
        "dataset_id": m.dataset_id,
        "mlflow_run_id": m.mlflow_run_id,
    }
