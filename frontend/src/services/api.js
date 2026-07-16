import axios from "axios";

const API_BASE_URL = process.env.REACT_APP_API_URL || "http://localhost:8000";

const api = axios.create({ baseURL: API_BASE_URL });

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("cs_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem("cs_token");
      localStorage.removeItem("cs_user");
    }
    return Promise.reject(error);
  }
);

export const authApi = {
  register: (data) => api.post("/api/auth/register", data),
  login: (data) => api.post("/api/auth/login", data),
  me: () => api.get("/api/auth/me"),
  roles: () => api.get("/api/auth/roles"),
};

export const modelsApi = {
  list: () => api.get("/api/models"),
  get: (id) => api.get(`/api/models/${id}`),
  train: (data) => api.post("/api/models/train", data),
  predict: (data) => api.post("/api/models/predict", data),
  // MLflow experiment tracking history for a model (additive)
  mlflowHistory: (id) => api.get(`/api/models/${id}/mlflow-history`),
  // Automated retraining trigger rule evaluation for a model (additive)
  retrainingTriggers: (id) => api.get(`/api/models/${id}/retraining-triggers`),
};

// Applicant Management Dashboard (Feature 1)
export const applicantsApi = {
  list: () => api.get("/api/models/applicants"),
  get: (applicationId) => api.get(`/api/models/applicants/${applicationId}`),
};

// Dataset upload + validation pipeline (Feature 4)
export const datasetsApi = {
  requiredSchema: () => api.get("/api/datasets/required-schema"),
  list: () => api.get("/api/datasets"),
  upload: (file, onUploadProgress) => {
    const form = new FormData();
    form.append("file", file);
    return api.post("/api/datasets/upload", form, {
      headers: { "Content-Type": "multipart/form-data" },
      onUploadProgress,
    });
  },
  remove: (datasetId) => api.delete(`/api/datasets/${datasetId}`),
};

export const governanceApi = {
  runFairness: (modelId) => api.post(`/api/governance/fairness/${modelId}`),
  getFairness: (modelId) => api.get(`/api/governance/fairness/${modelId}`),
  runDrift: (data) => api.post("/api/governance/drift", data),
  getDriftHistory: (modelId) => api.get(`/api/governance/drift/${modelId}`),
  decide: (modelId) => api.post(`/api/governance/decide/${modelId}`),
  auditLogs: () => api.get("/api/governance/audit-logs"),
  // Model Comparison (Feature 2)
  compare: (modelIds) => api.get("/api/governance/compare", { params: { model_ids: modelIds.join(",") } }),
  // Automated Drift Monitoring + Alerts (Feature 8)
  setSchedule: (data) => api.post("/api/governance/schedule", data),
  getSchedule: (modelId) => api.get(`/api/governance/schedule/${modelId}`),
  listAlerts: () => api.get("/api/governance/alerts"),
  acknowledgeAlert: (alertId) => api.post(`/api/governance/alerts/${alertId}/acknowledge`),
};

// Role-Based Authentication + Configurable Thresholds (Features 6, 7)
export const adminApi = {
  listUsers: () => api.get("/api/admin/users"),
  updateUserRole: (userId, role) => api.put(`/api/admin/users/${userId}/role`, { role }),
  getThresholds: (userId) => api.get(`/api/admin/thresholds/${userId}`),
  updateThresholds: (data) => api.put("/api/admin/thresholds", data),
  approveDeployment: (data) => api.post("/api/admin/approve-deployment", data),
};

// Compliance Report Export (Feature 9)
export const reportsApi = {
  download: async (modelId, format) => {
    const response = await api.get(`/api/reports/${modelId}/export`, {
      params: { format },
      responseType: "blob",
    });
    const blob = new Blob([response.data], {
      type: format === "pdf" ? "application/pdf" : "text/csv",
    });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", `compliance_report_model_${modelId}.${format}`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.URL.revokeObjectURL(url);
  },
};

export default api;
