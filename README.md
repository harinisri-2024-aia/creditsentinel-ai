# CreditSentinel

**A monitoring shield for smarter and fairer lending models.**

CreditSentinel is an MLOps-based Responsible Machine Learning platform for credit risk model governance. It trains credit risk models, then continuously audits them for performance decay, fairness violations, and data drift — automatically deciding whether a model is safe to deploy.

> **See [UPDATE_NOTES.md](./UPDATE_NOTES.md) for the per-user ownership bug fix and the 10 features added in this revision** (applicant management, model comparison, SHAP-style explainability, dataset upload pipeline, bias mitigation suggestions, role-based auth, configurable fairness thresholds, automated drift monitoring, compliance report export, and UI polish).

## Core Workflow

```
Data → Model Training → Performance Evaluation → Fairness Audit
     → Governance Gate → Model Deployment → Continuous Monitoring → Retraining Trigger
```

A model is approved for production **only if** it passes BOTH the performance gate (accuracy/F1 thresholds) AND the fairness gate (disparate impact ≥ 0.8, equal opportunity difference ≤ 0.1 across gender, age group, and region — configurable per user by an Admin). If either check fails, deployment is automatically blocked, and bias mitigation suggestions are generated.

## Tech Stack

**Backend:** Python, FastAPI, SQLAlchemy (SQLite by default), scikit-learn, XGBoost, JWT auth, bcrypt password hashing, reportlab (PDF reports), openpyxl (XLSX dataset uploads).

**Frontend:** React, React Router, Tailwind CSS, Framer Motion, Recharts, Axios, lucide-react icons.

## Project Structure

```
creditsentinel/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app entrypoint + scheduler startup
│   │   ├── database.py              # SQLAlchemy models (incl. ownership, datasets, thresholds, schedules)
│   │   ├── api/                     # auth, model, governance, dataset, admin, report routes
│   │   ├── services/                # ml, fairness, drift, governance, dataset, threshold, scheduler services
│   │   └── utils/                   # auth (JWT + RBAC), explainability (SHAP-style), report (PDF/CSV)
│   ├── requirements.txt
│   └── .env
├── frontend/
│   ├── src/
│   │   ├── pages/                   # Home, Auth, Dashboard, Models, Monitoring, Applicants, Compare, Upload, Admin
│   │   ├── components/               # UI.jsx, Layout.jsx
│   │   ├── context/AuthContext.jsx
│   │   └── services/api.js
│   ├── package.json
│   └── .env
├── README.md
└── UPDATE_NOTES.md                  # Bug fix + feature changelog for this revision
```

## Quick Start

### 1. Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The API will be live at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.
A SQLite database file (`creditsentinel.db`) and trained model artifacts (`app/data/artifacts/`) are created automatically on first run.

### 2. Frontend

```bash
cd frontend
npm install
npm start
```

The app will be live at `http://localhost:3000`. It talks to the backend using the `REACT_APP_API_URL` variable in `frontend/.env` (defaults to `http://localhost:8000`).

### 3. Using the platform

1. **Register** an account on the landing page and pick a role (Data Scientist, Auditor, Loan Officer, or Admin).
2. Go to **Models** → choose an algorithm (XGBoost or Random Forest) and optionally a previously uploaded dataset → **Train New Model**. Without a dataset selected it trains on a built-in synthetic credit-risk dataset (income, credit score, debt, etc., with gender/age/region as sensitive attributes for fairness auditing).
3. Click **Run Fairness Audit + Governance Decision** to audit the model across gender, age group, and region, then issue an automated approve/reject decision. If it fails, bias mitigation suggestions are shown.
4. Go to **Monitoring** to re-run fairness audits, simulate data drift, schedule automated daily/weekly drift checks, and review alerts.
5. Use the **risk score calculator** on the Models page to score an applicant and see the SHAP-style explanation and counterfactual factors. Every scored applicant appears in **Applicants**.
6. Use **Compare** to see metric/fairness/drift diffs across model versions, **Upload Dataset** to train on your own data, and **Admin** (Admin role only) to manage users, fairness thresholds, and deployment approvals.

## API Overview

| Endpoint | Description |
|---|---|
| `POST /api/auth/register` / `login` | Auth, returns JWT. `register` accepts an optional `role`. |
| `GET /api/models` | List **your own** trained model versions (Admin/Auditor see all) |
| `POST /api/models/train` | Train a new model version, optionally from an uploaded dataset |
| `POST /api/models/predict` | Score a single applicant (returns SHAP-style explanation + counterfactuals) |
| `GET /api/models/applicants` / `/{id}` | Applicant Management Dashboard |
| `POST /api/governance/fairness/{model_id}` | Run fairness audit (returns mitigation suggestions if failed) |
| `POST /api/governance/drift` | Simulate a production batch & run drift detection |
| `POST /api/governance/decide/{model_id}` | Run the performance + fairness governance gate |
| `GET /api/governance/audit-logs` | Audit trail (yours, or all for Admin/Auditor) |
| `GET /api/governance/compare?model_ids=1,2` | Compare two or more model versions |
| `POST /api/governance/schedule` | Configure automated drift monitoring (off/daily/weekly) |
| `GET /api/governance/alerts` | Drift alerts |
| `POST /api/datasets/upload` | Upload + validate a CSV/XLSX dataset |
| `GET /api/admin/users`, `PUT /api/admin/users/{id}/role` | User & role management (Admin) |
| `PUT /api/admin/thresholds` | Configure fairness thresholds (Admin) |
| `POST /api/admin/approve-deployment` | Manual deployment approval (Admin) |
| `GET /api/reports/{model_id}/export?format=pdf\|csv` | Compliance report export |

## Notes

- The dataset is synthetically generated at training time by default; upload your own via **Upload Dataset** or swap `ml_service.get_dataset()` for a real data source.
- Default governance thresholds: accuracy ≥ 0.70, F1 ≥ 0.60, disparate impact ≥ 0.8, equal opportunity difference ≤ 0.1 (adjust per-user in `governance_service.py` / via the Admin thresholds UI).
- The default `SECRET_KEY` in `backend/.env` should be replaced before any real deployment.
