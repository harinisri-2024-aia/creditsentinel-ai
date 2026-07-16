import React, { useEffect, useState } from "react";
import { ShieldCheck, Users, SlidersHorizontal, CheckCircle2, XCircle } from "lucide-react";
import { DashboardLayout } from "../components/Layout";
import { Card, Button, Select, Input, Spinner, EmptyState } from "../components/UI";
import { adminApi, modelsApi } from "../services/api";
import { useAuth } from "../context/AuthContext";

const ROLES = ["admin", "data_scientist", "auditor", "loan_officer"];

export default function AdminPage() {
  const { hasRole } = useAuth();
  const [users, setUsers] = useState([]);
  const [models, setModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [thresholdUserId, setThresholdUserId] = useState("");
  const [diMin, setDiMin] = useState(0.8);
  const [eodMax, setEodMax] = useState(0.1);
  const [savingThresholds, setSavingThresholds] = useState(false);
  const [thresholdMsg, setThresholdMsg] = useState(null);

  const isAdmin = hasRole("admin");

  useEffect(() => {
    if (!isAdmin) {
      setLoading(false);
      return;
    }
    Promise.all([adminApi.listUsers(), modelsApi.list()])
      .then(([usersRes, modelsRes]) => {
        setUsers(usersRes.data);
        setModels(modelsRes.data);
      })
      .finally(() => setLoading(false));
  }, [isAdmin]);

  const handleRoleChange = async (userId, role) => {
    const res = await adminApi.updateUserRole(userId, role);
    setUsers((prev) => prev.map((u) => (u.id === userId ? { ...u, role: res.data.role } : u)));
  };

  const loadThresholdsFor = async (userId) => {
    setThresholdUserId(userId);
    if (!userId) return;
    const res = await adminApi.getThresholds(userId);
    setDiMin(res.data.disparate_impact_min);
    setEodMax(res.data.equal_opportunity_max);
  };

  const saveThresholds = async () => {
    setSavingThresholds(true);
    setThresholdMsg(null);
    try {
      await adminApi.updateThresholds({
        user_id: parseInt(thresholdUserId, 10),
        disparate_impact_min: parseFloat(diMin),
        equal_opportunity_max: parseFloat(eodMax),
      });
      setThresholdMsg({ ok: true, text: "Thresholds updated." });
    } catch (e) {
      setThresholdMsg({ ok: false, text: e?.response?.data?.detail || "Failed to update thresholds." });
    } finally {
      setSavingThresholds(false);
    }
  };

  const handleDeploymentDecision = async (modelId, approve) => {
    await adminApi.approveDeployment({ model_id: modelId, approve });
    const res = await modelsApi.list();
    setModels(res.data);
  };

  if (!isAdmin) {
    return (
      <DashboardLayout>
        <Card>
          <EmptyState
            icon={<ShieldCheck size={32} />}
            title="Admin access required"
            subtitle="This page manages users, roles, fairness thresholds, and deployment approvals. Ask an existing Admin to grant you access."
          />
        </Card>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1">Admin</h1>
        <p className="text-muted text-sm">Manage users and roles, configure fairness thresholds, and approve model deployments.</p>
      </div>

      {loading ? (
        <Spinner />
      ) : (
        <div className="grid lg:grid-cols-2 gap-6">
          <Card>
            <h3 className="font-semibold mb-4 flex items-center gap-2"><Users size={18} /> Users &amp; Roles</h3>
            {users.length === 0 ? (
              <EmptyState icon={<Users size={28} />} title="No users found" />
            ) : (
              <div className="space-y-2">
                {users.map((u) => (
                  <div key={u.id} className="flex items-center justify-between p-3 rounded-xl border border-white/10 text-sm">
                    <div>
                      <p className="font-medium">{u.full_name}</p>
                      <p className="text-muted text-xs">{u.email}</p>
                    </div>
                    <select
                      className="input-field w-auto py-1.5 text-xs"
                      value={u.role}
                      onChange={(e) => handleRoleChange(u.id, e.target.value)}
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>{r.replaceAll("_", " ")}</option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card>
            <h3 className="font-semibold mb-4 flex items-center gap-2"><SlidersHorizontal size={18} /> Configurable Fairness Thresholds</h3>
            <Select
              label="user"
              options={[{ value: "", label: "Select a user..." }, ...users.map((u) => ({ value: String(u.id), label: `${u.full_name} (${u.email})` }))]}
              value={thresholdUserId}
              onChange={(e) => loadThresholdsFor(e.target.value)}
            />
            {thresholdUserId && (
              <>
                <Input
                  label="disparate impact threshold (minimum, 0–1)"
                  type="number" step="0.01" min="0" max="1"
                  value={diMin}
                  onChange={(e) => setDiMin(e.target.value)}
                />
                <Input
                  label="equal opportunity difference threshold (maximum, 0–1)"
                  type="number" step="0.01" min="0" max="1"
                  value={eodMax}
                  onChange={(e) => setEodMax(e.target.value)}
                />
                <Button onClick={saveThresholds} disabled={savingThresholds}>
                  {savingThresholds ? "Saving..." : "Save Thresholds"}
                </Button>
                {thresholdMsg && (
                  <p className={`text-sm mt-3 ${thresholdMsg.ok ? "text-accent" : "text-red-400"}`}>{thresholdMsg.text}</p>
                )}
              </>
            )}
          </Card>

          <Card className="lg:col-span-2">
            <h3 className="font-semibold mb-4 flex items-center gap-2"><ShieldCheck size={18} /> Deployment Approval</h3>
            {models.length === 0 ? (
              <EmptyState icon={<ShieldCheck size={28} />} title="No models to review" />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-muted text-left border-b border-white/10">
                      <th className="py-2 pr-4">Model</th>
                      <th className="py-2 pr-4">Accuracy</th>
                      <th className="py-2 pr-4">Fairness</th>
                      <th className="py-2 pr-4">Status</th>
                      <th className="py-2 pr-4">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {models.map((m) => (
                      <tr key={m.id} className="border-b border-white/5">
                        <td className="py-3 pr-4">{m.name} {m.version}</td>
                        <td className="py-3 pr-4">{(m.accuracy * 100).toFixed(1)}%</td>
                        <td className="py-3 pr-4 capitalize">{m.fairness_status}</td>
                        <td className="py-3 pr-4 capitalize">{m.status}</td>
                        <td className="py-3 pr-4">
                          <div className="flex gap-2">
                            <button
                              onClick={() => handleDeploymentDecision(m.id, true)}
                              className="text-accent hover:text-accent/80"
                              title="Approve deployment"
                            >
                              <CheckCircle2 size={18} />
                            </button>
                            <button
                              onClick={() => handleDeploymentDecision(m.id, false)}
                              className="text-red-400 hover:text-red-300"
                              title="Reject deployment"
                            >
                              <XCircle size={18} />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </div>
      )}
    </DashboardLayout>
  );
}
