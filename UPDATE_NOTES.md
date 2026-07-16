# CreditSentinel — Update Notes (this revision)

This revision keeps the existing frontend (React) and backend (FastAPI) and
modifies it in place — nothing was rebuilt from scratch. This document
explains the critical bug fix and the 10 features added on top of it.

## Critical bug fix: per-user model ownership

**Problem:** `GET /api/models` (and several related endpoints) queried
`ModelVersion` globally with no filter on the owning user. Two different
users each training "Model v1" caused **both** dashboards to report
`Total Models: 2` instead of `1` each.

**Root cause:** `ModelVersion.created_by` already existed in the schema,
but nothing in `api/model_routes.py` or `api/governance_routes.py` actually
filtered by it — `Prediction`, `FairnessAudit`, and `DriftReport` had no
ownership column at all.

**Fix:**
- `backend/app/database.py` — added `user_id` ownership columns to
  `Prediction`, `FairnessAudit`, `DriftReport`. Added a light auto-migration
  (`_run_light_migrations`) that adds the missing columns to an existing
  SQLite file and backfills `user_id` on any pre-existing rows by joining
  through `ModelVersion.created_by`, so upgrading an existing database in
  place doesn't lose data or crash on startup.
- `backend/app/api/model_routes.py` — `list_models`, `get_model`,
  `train_model` (version numbering — "v1.0" is now scoped per-user, not
  global), `predict`, and the new applicant endpoints all filter by
  `created_by` / `user_id`. Admins and Auditors get cross-user visibility
  (needed for governance/compliance oversight); Data Scientists and Loan
  Officers only ever see their own data.
- `backend/app/api/governance_routes.py` — `audit-logs`, fairness, drift,
  alerts, and schedule endpoints scoped the same way.

**Verified** with an automated test simulating the exact scenario in the
request (Harini and John both training "Model v1"): each now correctly sees
`Total Models: 1`, not `2`. Cross-user access to another user's model,
applicant record, or audit log returns `404`, not leaked data.

## New features

1. **Applicant Management Dashboard** — `GET /api/models/applicants` and
   `GET /api/models/applicants/{id}` (new endpoints in `model_routes.py`).
   New frontend page `ApplicantsPage.jsx`: list view (ID, name, risk score,
   prediction, decision, model version, date) with a detail drawer
   (prediction, risk score, SHAP-style explanation, counterfactual factors).
2. **Model Comparison** — `GET /api/governance/compare?model_ids=1,2` (new
   endpoint in `governance_routes.py`). New frontend page `ComparePage.jsx`:
   pick 2+ models, see accuracy/fairness/drift/governance diffs against the
   first selected model as baseline.
3. **Explainable AI Upgrade** — new `backend/app/utils/explainability.py`
   computes SHAP-style signed feature contributions via marginal ablation
   (no `shap` package dependency — works with any sklearn-compatible model).
   `ml_service.predict_single` now returns `shap_explanation` (signed,
   directional contributions in probability points) and `counterfactuals`
   ("what would change this decision") alongside the original
   `feature_importances_`-based `explanation` (kept for backward
   compatibility). Rendered as a directional bar chart in `ModelsPage.jsx`
   and `ApplicantsPage.jsx`.
4. **Dataset Upload & Training Pipeline** — new `api/dataset_routes.py` +
   `services/dataset_service.py`. Flow: upload CSV/XLSX → validate columns
   (`ml_service.validate_uploaded_dataset`, checking the 8 feature columns,
   3 sensitive attributes, and binary target) → train (`ml_service.train_model`
   now accepts an optional `dataset_df`) → evaluate → fairness check →
   register model version — using the existing ML pipeline end-to-end, not
   a separate one. New frontend page `UploadPage.jsx`.
5. **Bias Mitigation Suggestions** — `fairness_service.generate_mitigation_suggestions`
   (new function) returns concrete suggestions — remove/de-weight a
   correlated feature, rebalance the dataset, apply a per-group decision
   threshold, retrain with a fairness-aware objective — whenever a fairness
   audit fails, instead of only rejecting. Surfaced in both `ModelsPage.jsx`
   and `MonitoringPage.jsx`.
6. **Role-Based Authentication** — 4 roles (`admin`, `data_scientist`,
   `auditor`, `loan_officer`) added to `User.role`. New `require_role()`
   FastAPI dependency factory in `utils/auth.py` enforces the requested
   permission matrix (Data Scientist: train/upload; Auditor: view fairness
   reports/logs; Admin: manage users/approve deployment). Role is
   selectable at registration (`AuthPages.jsx`) and manageable afterward by
   Admins (`AdminPage.jsx`).
7. **Configurable Fairness Thresholds** — new `FairnessThreshold` table +
   `services/threshold_service.py`; Admin-only endpoints in new
   `api/admin_routes.py`; UI in `AdminPage.jsx`. Falls back to the previous
   hardcoded defaults (disparate impact ≥ 0.8, equal opportunity diff ≤ 0.1)
   when no override exists, so behavior is unchanged until an Admin
   explicitly customizes it for a user.
8. **Automated Drift Monitoring** — new `MonitoringSchedule` and
   `DriftAlert` tables, new `services/scheduler_service.py` (in-process
   asyncio loop started on FastAPI startup — no external cron/task-queue
   dependency). Daily/weekly scheduling control and an alerts panel (with
   acknowledge action) added to `MonitoringPage.jsx`.
9. **Compliance Report Export** — new `backend/app/utils/report.py` +
   `api/report_routes.py`: PDF (via `reportlab`) and CSV export covering
   model info, performance metrics, fairness results (with thresholds
   used), drift history, governance decision, and audit history. Export
   buttons added to `ModelsPage.jsx`.
10. **Dashboard polish** — new `EmptyState`, `ProgressBar`, `Skeleton`
    components added to `UI.jsx`; consistent empty/loading states applied
    across `DashboardPage.jsx`, `ModelsPage.jsx`, `MonitoringPage.jsx`, and
    all new pages. Dark theme, green accent, and existing visual language
    (`glass`, `btn-primary`, `badge-*` CSS classes) fully preserved —
    nothing in `styles/index.css` or `tailwind.config.js` was changed.

## Other fixes made along the way

- The registration form previously accepted untrimmed/empty values (visible
  in earlier testing as "None" being accepted as a literal company name and
  short/blank passwords going through). `AuthPages.jsx` now trims input and
  validates name length, email shape, and password length (min 8 chars)
  client-side before submitting; the backend's existing `EmailStr`
  validation on the Pydantic model was already correct and is unchanged.

## What did NOT change

- `HomePage.jsx` (marketing landing page) — untouched.
- `services/governance_service.py` (performance gate logic) — untouched;
  still algorithm-agnostic and didn't need ownership scoping since it's
  only ever called with a model already fetched by the route layer.
- `services/drift_service.py` (PSI-based drift detection) — untouched;
  reused as-is by both the manual and scheduled drift checks.
- Existing CSS / Tailwind theme — untouched.
- Existing `/api/auth/*`, `/api/models/train`, `/api/models/predict`,
  `/api/governance/fairness/*`, `/api/governance/drift`,
  `/api/governance/decide/*` endpoint *paths* and core response shapes —
  unchanged (only additive fields, e.g. `shap_explanation`); existing
  frontend calls to them did not need to change.

## Running it

```bash
# Backend
cd backend
python3 -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm start
```

The backend auto-creates/upgrades `creditsentinel.db` on first run.

**Creating the first Admin:** register normally and pick "Admin" from the
role dropdown on the sign-up page (or have an existing Admin promote you
via `PUT /api/admin/users/{id}/role`).

## New/changed file map

```
backend/app/database.py                  CHANGED — ownership columns, new tables, light migration
backend/app/main.py                       CHANGED — new routers wired up, scheduler startup
backend/app/utils/auth.py                 CHANGED — require_role() RBAC dependency
backend/app/utils/explainability.py       NEW — SHAP-style explanation + counterfactuals
backend/app/utils/report.py               NEW — PDF/CSV compliance report builder
backend/app/services/ml_service.py        CHANGED — dataset upload support, new explainability
backend/app/services/fairness_service.py  CHANGED — configurable thresholds, mitigation suggestions
backend/app/services/threshold_service.py NEW — per-user threshold resolution
backend/app/services/dataset_service.py   NEW — upload/validate/persist pipeline
backend/app/services/scheduler_service.py NEW — automated drift monitoring loop
backend/app/services/governance_service.py UNCHANGED
backend/app/services/drift_service.py     UNCHANGED
backend/app/api/auth_routes.py            CHANGED — role at registration
backend/app/api/model_routes.py           CHANGED — ownership fix, applicants endpoints
backend/app/api/governance_routes.py      CHANGED — ownership fix, compare/schedule/alerts/mitigation
backend/app/api/dataset_routes.py         NEW — upload pipeline endpoints
backend/app/api/admin_routes.py           NEW — users/roles/thresholds/deployment approval
backend/app/api/report_routes.py          NEW — compliance export endpoint
backend/requirements.txt                  CHANGED — added reportlab, openpyxl

frontend/src/services/api.js              CHANGED — new namespaced API groups (additive)
frontend/src/context/AuthContext.jsx      CHANGED — hasRole() helper
frontend/src/components/UI.jsx            CHANGED — EmptyState/ProgressBar/Skeleton (additive)
frontend/src/components/Layout.jsx        CHANGED — role-gated nav links
frontend/src/App.jsx                      CHANGED — new routes
frontend/src/pages/AuthPages.jsx          CHANGED — role select + input validation
frontend/src/pages/DashboardPage.jsx      CHANGED — EmptyState polish only
frontend/src/pages/ModelsPage.jsx         CHANGED — SHAP chart, mitigation, dataset select, export
frontend/src/pages/MonitoringPage.jsx     CHANGED — scheduling, alerts, mitigation
frontend/src/pages/ApplicantsPage.jsx     NEW
frontend/src/pages/ComparePage.jsx        NEW
frontend/src/pages/UploadPage.jsx         NEW
frontend/src/pages/AdminPage.jsx          NEW
frontend/src/pages/HomePage.jsx           UNCHANGED
```

---

# Update — Logistic Regression, Decision Tree, SHAP Waterfall, Retraining Triggers

This is a second, separate revision on top of everything above. Same rule
applied: **only additions** — nothing in the existing UI, pages, workflows,
or prior features was changed, removed, or redesigned. XGBoost and Random
Forest behave exactly as before.

## 1. Two new ML models: Logistic Regression, Decision Tree

- `backend/app/services/ml_service.py` — `train_model()` gained two new
  `elif` branches (`logistic_regression` → `sklearn.linear_model.LogisticRegression`,
  `decision_tree` → `sklearn.tree.DecisionTreeClassifier`), inserted before the
  existing `else` fallback. The original `xgboost`/`random_forest` branches
  are untouched. New `resolve_effective_params()` helper returns the actual
  hyperparameters used per algorithm (so only relevant params are recorded —
  e.g. a Decision Tree run doesn't store an irrelevant `learning_rate`).
- `backend/app/api/model_routes.py` — `TrainRequest` gained optional
  `C`, `max_iter`, `solver`, `min_samples_leaf`, `criterion` fields (all
  default-valued, ignored by xgboost/random_forest exactly like
  `learning_rate` was already ignored by random_forest).
- `frontend/src/pages/ModelsPage.jsx` — the algorithm dropdown gained two
  more options; a new "Algorithm" column was added to the Model Versions
  table so all four are distinguishable at a glance.
- Versioning, training history, the existing Model Versions table, and the
  **existing model comparison endpoint** (`GET /api/governance/compare`)
  all already worked generically off `ModelVersion.algorithm` as a plain
  string — so the two new algorithms appear there automatically, with zero
  changes needed to `governance_service.py`.

## 2. MLflow experiment tracking

- New `backend/app/services/mlflow_service.py`. Every training run (all four
  algorithms) is now also logged to MLflow: version, hyperparameters,
  accuracy/precision/recall/f1, and the trained model artifact itself.
  Uses a local SQLite-backed tracking store at
  `backend/app/data/mlflow/mlflow.db` (created automatically — no external
  MLflow server required). Browse it anytime with:
  ```bash
  mlflow ui --backend-store-uri sqlite:///app/data/mlflow/mlflow.db
  ```
- Designed to **never** break training: if `mlflow` is missing or
  misconfigured, logging is silently skipped (a warning is logged) and the
  rest of the app behaves exactly as before.
- New endpoint `GET /api/models/{id}/mlflow-history` returns the MLflow run
  history for a given model. `model_versions` gained one new nullable
  column, `mlflow_run_id` (applied via the existing light-migration
  mechanism — no data loss on upgrade).
- `requirements.txt` — added `shap` and `mlflow` (version-ranged, not
  pinned exactly, since both pull in `numpy`/`scipy` and the exact pin
  combination matters; the ranges chosen were verified to install cleanly
  alongside the existing `numpy==1.26.4` pin).

## 3. SHAP waterfall chart

- `backend/app/utils/explainability.py` — new `compute_expected_risk_score()`
  and `build_shap_waterfall()` functions. They reshape the *existing*
  signed per-feature contributions (already computed by `explain_prediction()`
  for the original SHAP-style bar chart) into the canonical waterfall
  structure: a starting "expected value" (the model's average predicted
  risk), a sequence of cumulative steps, and a final value equal to this
  prediction's risk score. The contributions are proportionally rescaled so
  the steps always add up exactly to the final score (true SHAP explainers
  guarantee this "additivity" property by construction; the existing
  ablation-based method approximates it, so a small correction keeps the
  chart visually honest). Each feature's direction and relative impact are
  preserved unchanged — only the overall scale is corrected, and the
  original unscaled numbers stay available as `raw_contribution`.
- `ml_service.predict_single()` now also returns `shap_waterfall` alongside
  the existing `shap_explanation` and `counterfactuals` (additive key, old
  consumers of the response are unaffected).
- `frontend/src/pages/ModelsPage.jsx` — new `ShapWaterfallChart` component,
  rendered directly under the existing SHAP bar chart on the prediction
  result panel (existing bar chart untouched). Shows risk score, decision,
  and the waterfall directly underneath the existing explanation.
- Persisted on every prediction (`Prediction.explanation` JSON gained one
  new key) so it's also retrievable later via the existing
  `GET /api/models/applicants/{id}` endpoint.

## 4. Automated retraining trigger rules

- New `backend/app/services/retraining_trigger_service.py` implementing the
  three requested rules exactly as specified:
  - **Data Drift**: PSI > 0.2 → "Retraining recommended due to data drift"
    (uses the existing `DriftReport.data_drift_score`, which is computed in
    the same spirit as PSI by the existing, untouched `drift_service.py`).
  - **Performance**: Accuracy < 85% → "Retraining recommended due to
    performance degradation" (uses the existing `ModelVersion.accuracy`).
  - **Fairness**: Disparate Impact Ratio < 0.8 OR Equal Opportunity
    Difference exceeds threshold → "Retraining recommended due to fairness
    violation" (uses the existing `FairnessAudit` rows; the Equal
    Opportunity threshold defaults to the same admin-configurable value the
    existing fairness audit already uses via `threshold_service.py`).
  - Each rule reports trigger name, current value, required threshold, and
    a reason string in the requested format, e.g.
    `"PSI = 0.35 exceeded allowed threshold 0.2"`.
  - Purely a read-only evaluation layer on top of data the existing drift
    and fairness features already compute — does not change how drift,
    fairness, or accuracy are calculated, and does not touch the existing
    governance approve/reject workflow.
- New endpoint `GET /api/models/{id}/retraining-triggers`. Each evaluation
  is also persisted to a new `retraining_trigger_evaluations` table (new
  table only — no existing table touched) for history.
- `frontend/src/pages/MonitoringPage.jsx` — new "Retraining Trigger Rules"
  card added after the existing Drift Alerts card, with a "Re-check
  Triggers" button. Automatically re-checked after running a drift check or
  fairness audit from this same page (existing Drift/Fairness cards and
  their buttons are otherwise untouched).

## Known pre-existing issue (not introduced by this change, not fixed by it)

The uploaded `backend/creditsentinel.db` stores `model_versions.artifact_path`
as **absolute Windows paths** (e.g.
`C:\Users\Administrator\OneDrive\Desktop\creditsentinel_updated\backend\app\data\artifacts\model_1.joblib`)
for the 13 pre-existing models. This means **predicting on models 1–13**
will fail with a file-not-found error on any machine other than the exact
Windows machine those paths point to — this reproduces identically on the
original, completely unmodified codebase (verified before making any
changes here) and is unrelated to anything in this update. Newly trained
models (14+, including the new Logistic Regression/Decision Tree runs) save
artifacts using a path relative to wherever the app is actually running, so
they aren't affected. If you need models 1–13 to predict correctly in your
environment, retrain them (same name/algorithm) to get a fresh, correct
artifact path, or update `artifact_path` in the database for those rows.

## New/changed file map (this revision)

```
backend/app/database.py                        CHANGED — +mlflow_run_id column, +RetrainingTriggerEvaluation table
backend/app/services/ml_service.py              CHANGED — +logistic_regression/+decision_tree, +resolve_effective_params, +shap_waterfall in predict_single
backend/app/services/mlflow_service.py          NEW — MLflow experiment tracking integration
backend/app/services/retraining_trigger_service.py NEW — drift/performance/fairness trigger rules
backend/app/utils/explainability.py             CHANGED — +compute_expected_risk_score, +build_shap_waterfall
backend/app/api/model_routes.py                 CHANGED — new hyperparameter fields, MLflow logging, +2 endpoints
backend/requirements.txt                        CHANGED — added shap, mlflow

frontend/src/services/api.js                    CHANGED — +mlflowHistory, +retrainingTriggers (additive)
frontend/src/pages/ModelsPage.jsx               CHANGED — +2 algorithm options, +Algorithm column, +ShapWaterfallChart
frontend/src/pages/MonitoringPage.jsx           CHANGED — +Retraining Trigger Rules card

UNCHANGED (this revision): everything else, including governance_service.py,
drift_service.py, fairness_service.py, threshold_service.py,
scheduler_service.py, dataset_service.py, all auth/admin/dataset/report
routes, App.jsx, Layout.jsx, UI.jsx, HomePage.jsx, ApplicantsPage.jsx,
ComparePage.jsx, UploadPage.jsx, AdminPage.jsx, AuthPages.jsx,
DashboardPage.jsx, and all CSS/Tailwind theming.
```

