"""
MLflow experiment tracking integration (additive feature).

CreditSentinel already tracks model versions, params, and metrics in its own
SQL database (ModelVersion table) — that remains the system of record the
rest of the app reads from, completely unchanged. This module ADDS a parallel
MLflow experiment tracking layer on top: every training run (for all four
algorithms — XGBoost, Random Forest, Logistic Regression, Decision Tree) is
also logged to MLflow as its own run, with:

  - model version (run name / tag)
  - hyperparameters (mlflow.log_params)
  - metrics: accuracy, precision, recall, f1 (mlflow.log_metrics)
  - the trained model artifact itself (mlflow.sklearn.log_model)
  - training history, browsable via `mlflow ui` against the same tracking
    store this module writes to (see MLFLOW_TRACKING_URI below)

Design goals:
  - Zero impact on existing behavior if MLflow is missing/misconfigured.
    Every public function here is wrapped so a failure merely skips MLflow
    logging and logs a warning — it can never break model training,
    prediction, or any existing endpoint.
  - No external MLflow server required: defaults to a local SQLite-backed
    tracking store at backend/app/data/mlflow/mlflow.db, stored right next
    to the existing artifacts/datasets folders. A real MLFLOW_TRACKING_URI
    (e.g. a hosted MLflow server) can be set instead via .env.
"""
import os
import logging

logger = logging.getLogger("creditsentinel.mlflow")

MLFLOW_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "mlflow")
os.makedirs(MLFLOW_DIR, exist_ok=True)

DEFAULT_TRACKING_URI = f"sqlite:///{os.path.join(MLFLOW_DIR, 'mlflow.db')}"
EXPERIMENT_NAME = "CreditSentinel-Credit-Risk-Models"

_mlflow = None
_initialized = False
_available = False


def _get_mlflow():
    """
    Lazily imports and configures mlflow exactly once. Returns the mlflow
    module, or None if mlflow isn't installed / couldn't be configured —
    callers must handle the None case and simply skip tracking.
    """
    global _mlflow, _initialized, _available
    if _initialized:
        return _mlflow if _available else None

    _initialized = True
    try:
        import mlflow as _mlflow_module

        tracking_uri = os.getenv("MLFLOW_TRACKING_URI", DEFAULT_TRACKING_URI)
        _mlflow_module.set_tracking_uri(tracking_uri)
        _mlflow_module.set_experiment(EXPERIMENT_NAME)

        _mlflow = _mlflow_module
        _available = True
        logger.info("MLflow experiment tracking enabled (tracking_uri=%s)", tracking_uri)
    except Exception:
        logger.warning(
            "MLflow is not available — model training will continue without "
            "MLflow experiment tracking. Install `mlflow` to enable it.",
            exc_info=True,
        )
        _mlflow = None
        _available = False

    return _mlflow if _available else None


def is_available() -> bool:
    return _get_mlflow() is not None


def log_training_run(
    model,
    algorithm: str,
    version: str,
    model_name: str,
    params: dict,
    metrics: dict,
    dataset_label: str = "synthetic",
    model_db_id: int = None,
):
    """
    Logs one completed training run to MLflow. Safe to call unconditionally
    after every train_model() call for every algorithm — never raises.

    Returns the MLflow run_id (str) on success, or None if MLflow logging
    was skipped/failed for any reason.
    """
    mlflow = _get_mlflow()
    if mlflow is None:
        return None

    try:
        run_name = f"{model_name}-{version}-{algorithm}"
        with mlflow.start_run(run_name=run_name) as run:
            mlflow.set_tags({
                "algorithm": algorithm,
                "model_version": version,
                "model_name": model_name,
                "dataset": dataset_label,
                "creditsentinel_model_id": str(model_db_id) if model_db_id is not None else "",
            })
            mlflow.log_params({k: v for k, v in (params or {}).items() if v is not None})
            mlflow.log_metrics({k: float(v) for k, v in (metrics or {}).items() if v is not None})

            try:
                if algorithm == "xgboost":
                    import mlflow.xgboost
                    mlflow.xgboost.log_model(model, name="model")
                else:
                    import mlflow.sklearn
                    mlflow.sklearn.log_model(model, name="model")
            except Exception:
                # Model logging is best-effort (e.g. unsupported model type);
                # params/metrics are the part that matters most for tracking.
                logger.warning("MLflow model artifact logging skipped for run %s", run_name, exc_info=True)

            return run.info.run_id
    except Exception:
        logger.warning("MLflow run logging failed for model_id=%s", model_db_id, exc_info=True)
        return None


def get_run_history(model_db_id: int = None, algorithm: str = None, limit: int = 100):
    """
    Returns logged MLflow runs (most recent first) for the experiment tracking
    history UI, optionally filtered by CreditSentinel model id and/or
    algorithm. Returns [] if MLflow isn't available rather than raising, so
    the comparison/history endpoint always responds.
    """
    mlflow = _get_mlflow()
    if mlflow is None:
        return []

    try:
        experiment = mlflow.get_experiment_by_name(EXPERIMENT_NAME)
        if experiment is None:
            return []

        filter_parts = []
        if model_db_id is not None:
            filter_parts.append(f"tags.creditsentinel_model_id = '{model_db_id}'")
        if algorithm is not None:
            filter_parts.append(f"tags.algorithm = '{algorithm}'")
        filter_string = " and ".join(filter_parts) if filter_parts else ""

        runs_df = mlflow.search_runs(
            experiment_ids=[experiment.experiment_id],
            filter_string=filter_string,
            order_by=["start_time DESC"],
            max_results=limit,
        )
        if runs_df is None or runs_df.empty:
            return []

        history = []
        for _, row in runs_df.iterrows():
            history.append({
                "run_id": row.get("run_id"),
                "run_name": row.get("tags.mlflow.runName"),
                "algorithm": row.get("tags.algorithm"),
                "model_version": row.get("tags.model_version"),
                "model_name": row.get("tags.model_name"),
                "dataset": row.get("tags.dataset"),
                "params": {
                    col.replace("params.", ""): row[col]
                    for col in runs_df.columns
                    if col.startswith("params.") and row[col] is not None
                },
                "metrics": {
                    col.replace("metrics.", ""): row[col]
                    for col in runs_df.columns
                    if col.startswith("metrics.") and row[col] is not None
                },
                "start_time": str(row.get("start_time")) if row.get("start_time") is not None else None,
                "status": row.get("status"),
            })
        return history
    except Exception:
        logger.warning("MLflow run history lookup failed", exc_info=True)
        return []


def get_tracking_info() -> dict:
    """Small status payload the frontend can show (tracking URI + availability)."""
    mlflow = _get_mlflow()
    return {
        "available": mlflow is not None,
        "tracking_uri": os.getenv("MLFLOW_TRACKING_URI", DEFAULT_TRACKING_URI),
        "experiment_name": EXPERIMENT_NAME,
    }
