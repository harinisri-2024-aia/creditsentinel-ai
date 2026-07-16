import os
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score

from app.utils import explainability
from app.services import mlflow_service

try:
    from xgboost import XGBClassifier
    XGBOOST_AVAILABLE = True
except Exception:
    XGBOOST_AVAILABLE = False

# All algorithms selectable in the "Train New Model" UI. XGBoost and Random
# Forest are the original two; Logistic Regression and Decision Tree are
# additive and follow the exact same train/evaluate/explain pipeline.
SUPPORTED_ALGORITHMS = ["xgboost", "random_forest", "logistic_regression", "decision_tree"]

MODEL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "artifacts")
os.makedirs(MODEL_DIR, exist_ok=True)

FEATURE_COLUMNS = [
    "age", "annual_income", "credit_score", "loan_amount",
    "loan_term_months", "existing_debt", "employment_years", "num_credit_lines",
]
SENSITIVE_COLUMNS = ["gender", "age_group", "region"]
TARGET_COLUMN = "default"

# Columns a user-uploaded dataset must contain. Sensitive attributes are
# required too because the fairness audit can't run without them.
REQUIRED_COLUMNS = FEATURE_COLUMNS + SENSITIVE_COLUMNS + [TARGET_COLUMN]


def _synthesize_dataset(n=4000, seed=42):
    """Generate a synthetic credit-risk dataset used when no dataset is uploaded."""
    rng = np.random.default_rng(seed)
    age = rng.integers(21, 70, n)
    income = rng.normal(55000, 22000, n).clip(12000, 250000)
    credit_score = rng.normal(650, 90, n).clip(300, 850)
    loan_amount = rng.normal(18000, 9000, n).clip(1000, 100000)
    term = rng.choice([12, 24, 36, 48, 60], n)
    debt = rng.normal(8000, 6000, n).clip(0, 80000)
    emp_years = rng.integers(0, 35, n)
    credit_lines = rng.integers(0, 12, n)
    gender = rng.choice(["male", "female"], n)
    age_group = pd.cut(age, bins=[20, 30, 45, 60, 71], labels=["21-30", "31-45", "46-60", "61-70"])
    region = rng.choice(["north", "south", "east", "west"], n)

    risk_score = (
        (850 - credit_score) * 0.5
        + debt * 0.02
        - income * 0.001
        + loan_amount * 0.01
        - emp_years * 5
        + rng.normal(0, 40, n)
    )
    default = (risk_score > np.percentile(risk_score, 70)).astype(int)

    df = pd.DataFrame({
        "age": age, "annual_income": income, "credit_score": credit_score,
        "loan_amount": loan_amount, "loan_term_months": term, "existing_debt": debt,
        "employment_years": emp_years, "num_credit_lines": credit_lines,
        "gender": gender, "age_group": age_group.astype(str), "region": region,
        "default": default,
    })
    return df


def get_dataset():
    return _synthesize_dataset()


def validate_uploaded_dataset(df: pd.DataFrame):
    """
    Validates that an uploaded CSV/dataset has the columns CreditSentinel's
    pipeline needs: the 8 model features, the 3 sensitive attributes used for
    fairness auditing, and the binary target column ('default': 0/1).

    Returns (is_valid: bool, message: str).
    """
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        return False, f"Missing required column(s): {', '.join(missing)}"

    if len(df) < 50:
        return False, "Dataset must contain at least 50 rows for a meaningful train/test split."

    unique_targets = set(df[TARGET_COLUMN].dropna().unique().tolist())
    if not unique_targets.issubset({0, 1}):
        return False, "Target column 'default' must be binary (0 = no default, 1 = default)."

    for col in FEATURE_COLUMNS:
        if not pd.api.types.is_numeric_dtype(df[col]):
            return False, f"Feature column '{col}' must be numeric."
        if df[col].isnull().any():
            return False, f"Feature column '{col}' contains missing values. Please clean the dataset and re-upload."

    return True, "Dataset validated successfully."


def resolve_effective_params(algorithm: str, params: dict = None) -> dict:
    """
    Returns the actual hyperparameters that train_model() will use for the
    given algorithm (defaults filled in), for tracking purposes (the
    ModelVersion DB row and MLflow logging both call this so what's recorded
    always matches what was actually trained).
    """
    params = params or {}
    if algorithm == "xgboost":
        return {
            "n_estimators": params.get("n_estimators", 150),
            "max_depth": params.get("max_depth", 5),
            "learning_rate": params.get("learning_rate", 0.1),
        }
    if algorithm == "logistic_regression":
        return {
            "C": params.get("C", 1.0),
            "max_iter": params.get("max_iter", 1000),
            "solver": params.get("solver", "lbfgs"),
        }
    if algorithm == "decision_tree":
        return {
            "max_depth": params.get("max_depth", 6),
            "min_samples_leaf": params.get("min_samples_leaf", 5),
            "criterion": params.get("criterion", "gini"),
        }
    # random_forest (also the fallback for any unrecognized algorithm)
    return {
        "n_estimators": params.get("n_estimators", 150),
        "max_depth": params.get("max_depth", 8),
    }


def train_model(algorithm: str = "xgboost", params: dict = None, dataset_df: pd.DataFrame = None):
    """
    Trains a model either on a user-uploaded dataset (dataset_df) or, if none
    is provided, on the built-in synthetic dataset — preserving the original
    one-click "Train New Model" behavior.
    """
    params = params or {}
    df = dataset_df if dataset_df is not None else get_dataset()
    X = df[FEATURE_COLUMNS]
    y = df[TARGET_COLUMN]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42,
        stratify=y if y.nunique() > 1 else None,
    )

    scaler = StandardScaler()
    X_train_s = scaler.fit_transform(X_train)
    X_test_s = scaler.transform(X_test)

    if algorithm == "xgboost" and XGBOOST_AVAILABLE:
        model = XGBClassifier(
            n_estimators=params.get("n_estimators", 150),
            max_depth=params.get("max_depth", 5),
            learning_rate=params.get("learning_rate", 0.1),
            use_label_encoder=False,
            eval_metric="logloss",
            random_state=42,
        )
    elif algorithm == "logistic_regression":
        model = LogisticRegression(
            C=params.get("C", 1.0),
            max_iter=params.get("max_iter", 1000),
            solver=params.get("solver", "lbfgs"),
            random_state=42,
        )
    elif algorithm == "decision_tree":
        model = DecisionTreeClassifier(
            max_depth=params.get("max_depth", 6),
            min_samples_leaf=params.get("min_samples_leaf", 5),
            criterion=params.get("criterion", "gini"),
            random_state=42,
        )
    else:
        algorithm = "random_forest"
        model = RandomForestClassifier(
            n_estimators=params.get("n_estimators", 150),
            max_depth=params.get("max_depth", 8),
            random_state=42,
        )

    model.fit(X_train_s, y_train)
    y_pred = model.predict(X_test_s)

    metrics = {
        "accuracy": float(accuracy_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred, zero_division=0)),
        "recall": float(recall_score(y_test, y_pred, zero_division=0)),
        "f1": float(f1_score(y_test, y_pred, zero_division=0)),
    }

    # Save test set with sensitive attributes for fairness/drift audits
    test_idx = X_test.index
    eval_df = df.loc[test_idx].copy()
    eval_df["prediction"] = y_pred

    # Baseline means (from the training split) power the SHAP-style explainer's
    # feature-ablation baseline ("what does an average applicant look like?").
    baseline_means = explainability.compute_baseline_means(X_train, FEATURE_COLUMNS)

    return model, scaler, algorithm, metrics, eval_df, baseline_means


def save_artifact(model, scaler, model_id: int, baseline_means: dict = None) -> str:
    path = os.path.join(MODEL_DIR, f"model_{model_id}.joblib")
    joblib.dump({
        "model": model,
        "scaler": scaler,
        "features": FEATURE_COLUMNS,
        "baseline_means": baseline_means or {},
    }, path)
    return path


def load_artifact(path: str):
    return joblib.load(path)


def predict_single(artifact_path: str, payload: dict):
    bundle = load_artifact(artifact_path)
    model, scaler, features = bundle["model"], bundle["scaler"], bundle["features"]
    baseline_means = bundle.get("baseline_means") or {}

    row = pd.DataFrame([{f: payload.get(f, 0) for f in features}])
    row_s = scaler.transform(row)
    proba = model.predict_proba(row_s)[0][1]
    pred = int(proba > 0.5)
    decision = "DECLINE" if pred == 1 else "APPROVE"

    # Legacy-shape explanation (kept so any older client code / tests relying
    # on raw feature_importances_ keeps working unchanged).
    if hasattr(model, "feature_importances_"):
        importances = model.feature_importances_
        contrib = sorted(
            zip(features, importances, row.iloc[0].values),
            key=lambda x: x[1], reverse=True,
        )[:5]
        legacy_explanation = [
            {"feature": f, "importance": float(imp), "value": float(val)}
            for f, imp, val in contrib
        ]
    else:
        legacy_explanation = []

    # New SHAP-style signed contribution explanation.
    if not baseline_means:
        baseline_means = {f: float(row.iloc[0][f]) for f in features}
    shap_style = explainability.explain_prediction(model, scaler, features, row, baseline_means)
    counterfactuals = explainability.counterfactual_suggestion(shap_style["contributions"], decision)

    # SHAP waterfall chart data (additive): reshapes the same signed
    # contributions above into a cumulative waterfall from the model's
    # average ("expected") risk score to this specific prediction's risk
    # score, for the waterfall chart on the prediction page.
    expected_risk_score = explainability.compute_expected_risk_score(model, scaler, features, baseline_means)
    shap_waterfall = explainability.build_shap_waterfall(
        shap_style["contributions"], shap_style["base_risk_score"], expected_risk_score,
    )

    return {
        "risk_score": round(float(proba) * 100, 2),
        "decision": decision,
        "explanation": legacy_explanation,
        "shap_explanation": shap_style["contributions"],
        "shap_waterfall": shap_waterfall,
        "counterfactuals": counterfactuals,
    }
