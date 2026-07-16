import React, { useEffect, useState } from "react";
import { GitCompare, ArrowRight } from "lucide-react";
import { DashboardLayout } from "../components/Layout";
import { Card, Badge, Spinner, EmptyState, Button } from "../components/UI";
import { modelsApi, governanceApi } from "../services/api";

export default function ComparePage() {
  const [models, setModels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedIds, setSelectedIds] = useState([]);
  const [comparing, setComparing] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    modelsApi.list().then((res) => setModels(res.data)).finally(() => setLoading(false));
  }, []);

  const toggleSelect = (id) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const runCompare = async () => {
    setError(null);
    setResult(null);
    if (selectedIds.length < 2) {
      setError("Select at least two models to compare.");
      return;
    }
    setComparing(true);
    try {
      const res = await governanceApi.compare(selectedIds);
      setResult(res.data);
    } catch (e) {
      setError(e?.response?.data?.detail || "Comparison failed.");
    } finally {
      setComparing(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1">Model Comparison</h1>
        <p className="text-muted text-sm">Select two or more model versions to compare accuracy, fairness, drift, and deployment outcomes.</p>
      </div>

      <Card className="mb-6">
        <h3 className="font-semibold mb-4 flex items-center gap-2"><GitCompare size={18} /> Select models to compare</h3>
        {loading ? (
          <Spinner />
        ) : models.length === 0 ? (
          <EmptyState icon={<GitCompare size={28} />} title="No models yet" subtitle="Train at least two models in the Models tab first." />
        ) : (
          <div className="flex flex-wrap gap-2">
            {models.map((m) => {
              const active = selectedIds.includes(m.id);
              return (
                <button
                  key={m.id}
                  onClick={() => toggleSelect(m.id)}
                  className={`px-4 py-2 rounded-xl text-sm border transition ${
                    active ? "bg-accent/20 border-accent text-accent" : "border-white/10 text-muted hover:border-white/30"
                  }`}
                >
                  {m.name} {m.version}
                </button>
              );
            })}
          </div>
        )}
        <div className="mt-5">
          <Button onClick={runCompare} disabled={comparing || selectedIds.length < 2}>
            {comparing ? "Comparing..." : "Compare Selected"}
          </Button>
          {error && <p className="text-red-400 text-sm mt-3">{error}</p>}
        </div>
      </Card>

      {result && (
        <>
          <Card className="mb-6">
            <h3 className="font-semibold mb-4">Side-by-side metrics</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-muted text-left border-b border-white/10">
                    <th className="py-2 pr-4">Model</th>
                    <th className="py-2 pr-4">Algorithm</th>
                    <th className="py-2 pr-4">Accuracy</th>
                    <th className="py-2 pr-4">F1</th>
                    <th className="py-2 pr-4">Fairness</th>
                    <th className="py-2 pr-4">Status</th>
                    <th className="py-2 pr-4">Governance</th>
                    <th className="py-2 pr-4">Latest Data Drift</th>
                  </tr>
                </thead>
                <tbody>
                  {result.models.map((m) => (
                    <tr key={m.id} className="border-b border-white/5">
                      <td className="py-3 pr-4 font-medium">{m.name} {m.version}</td>
                      <td className="py-3 pr-4 text-muted">{m.algorithm}</td>
                      <td className="py-3 pr-4">{(m.accuracy * 100).toFixed(1)}%</td>
                      <td className="py-3 pr-4">{(m.f1 * 100).toFixed(1)}%</td>
                      <td className="py-3 pr-4"><Badge status={m.fairness_status === "passed" ? "passed" : m.fairness_status === "failed" ? "failed" : "pending"} /></td>
                      <td className="py-3 pr-4"><Badge status={m.status} /></td>
                      <td className="py-3 pr-4"><Badge status={m.governance_decision} /></td>
                      <td className="py-3 pr-4 text-muted">{m.latest_data_drift_score ?? "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>

          <Card>
            <h3 className="font-semibold mb-4 flex items-center gap-2">
              <ArrowRight size={18} /> Differences vs. {result.models[0].name} {result.models[0].version} (baseline)
            </h3>
            <div className="space-y-4">
              {result.diffs.map((d) => {
                const target = result.models.find((m) => m.id === d.model_id);
                return (
                  <div key={d.model_id} className="border border-white/10 rounded-xl p-4">
                    <p className="font-medium mb-3">{target.name} {target.version}</p>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                      <div>
                        <p className="text-muted text-xs">Accuracy diff</p>
                        <p className={d.accuracy_diff >= 0 ? "text-accent" : "text-red-400"}>
                          {d.accuracy_diff >= 0 ? "+" : ""}{(d.accuracy_diff * 100).toFixed(1)} pts
                        </p>
                      </div>
                      <div>
                        <p className="text-muted text-xs">F1 diff</p>
                        <p className={d.f1_diff >= 0 ? "text-accent" : "text-red-400"}>
                          {d.f1_diff >= 0 ? "+" : ""}{(d.f1_diff * 100).toFixed(1)} pts
                        </p>
                      </div>
                      <div>
                        <p className="text-muted text-xs">Fairness changed</p>
                        <p>{d.fairness_changed ? "Yes" : "No"}</p>
                      </div>
                      <div>
                        <p className="text-muted text-xs">Drift diff</p>
                        <p>{d.drift_diff ?? "—"}</p>
                      </div>
                    </div>
                    {d.deployment_decision_changed && (
                      <p className="text-xs text-yellow-400 mt-3">⚠ Deployment decision differs from baseline</p>
                    )}
                  </div>
                );
              })}
            </div>
          </Card>
        </>
      )}
    </DashboardLayout>
  );
}
