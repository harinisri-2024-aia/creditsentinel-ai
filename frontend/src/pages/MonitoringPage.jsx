import React, { useEffect, useState } from "react";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Activity, Scale, RefreshCcw, Bell, Lightbulb, Clock, ShieldAlert } from "lucide-react";
import { DashboardLayout } from "../components/Layout";
import { Card, Select, Button, Badge, Spinner, EmptyState } from "../components/UI";
import { modelsApi, governanceApi } from "../services/api";

export default function MonitoringPage() {
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState(null);
  const [loading, setLoading] = useState(true);
  const [fairness, setFairness] = useState([]);
  const [mitigations, setMitigations] = useState([]);
  const [driftHistory, setDriftHistory] = useState([]);
  const [driftIntensity, setDriftIntensity] = useState(0.2);
  const [running, setRunning] = useState(false);
  const [schedule, setSchedule] = useState({ frequency: "off", drift_intensity: 0.2 });
  const [savingSchedule, setSavingSchedule] = useState(false);
  const [alerts, setAlerts] = useState([]);
  // Automated Retraining Trigger Rules (additive)
  const [retrainingTriggers, setRetrainingTriggers] = useState(null);
  const [checkingTriggers, setCheckingTriggers] = useState(false);

  useEffect(() => {
    modelsApi.list().then((res) => {
      setModels(res.data);
      if (res.data.length) setSelectedModel(res.data[0].id);
    }).finally(() => setLoading(false));
    governanceApi.listAlerts().then((res) => setAlerts(res.data));
  }, []);

  useEffect(() => {
    if (!selectedModel) return;
    governanceApi.getFairness(selectedModel).then((res) => {
      setFairness(res.data.results || res.data); // tolerate either shape
      setMitigations(res.data.mitigation_suggestions || []);
    });
    governanceApi.getDriftHistory(selectedModel).then((res) => setDriftHistory(res.data));
    governanceApi.getSchedule(selectedModel).then((res) => setSchedule(res.data));
    modelsApi.retrainingTriggers(selectedModel).then((res) => setRetrainingTriggers(res.data)).catch(() => setRetrainingTriggers(null));
  }, [selectedModel]);

  const checkRetrainingTriggers = async () => {
    if (!selectedModel) return;
    setCheckingTriggers(true);
    try {
      const res = await modelsApi.retrainingTriggers(selectedModel);
      setRetrainingTriggers(res.data);
    } finally {
      setCheckingTriggers(false);
    }
  };

  const runDriftCheck = async () => {
    if (!selectedModel) return;
    setRunning(true);
    try {
      await governanceApi.runDrift({ model_id: selectedModel, drift_intensity: driftIntensity });
      const res = await governanceApi.getDriftHistory(selectedModel);
      setDriftHistory(res.data);
      const alertsRes = await governanceApi.listAlerts();
      setAlerts(alertsRes.data);
      checkRetrainingTriggers();
    } finally {
      setRunning(false);
    }
  };

  const runFairnessCheck = async () => {
    if (!selectedModel) return;
    setRunning(true);
    try {
      const res = await governanceApi.runFairness(selectedModel);
      setFairness(res.data.results || []);
      setMitigations(res.data.mitigation_suggestions || []);
      checkRetrainingTriggers();
    } finally {
      setRunning(false);
    }
  };

  const updateSchedule = async (frequency) => {
    if (!selectedModel) return;
    setSavingSchedule(true);
    try {
      const res = await governanceApi.setSchedule({
        model_id: selectedModel,
        frequency,
        drift_intensity: schedule.drift_intensity || 0.2,
      });
      setSchedule(res.data);
    } finally {
      setSavingSchedule(false);
    }
  };

  const acknowledgeAlert = async (alertId) => {
    await governanceApi.acknowledgeAlert(alertId);
    setAlerts((prev) => prev.map((a) => (a.id === alertId ? { ...a, acknowledged: true } : a)));
  };

  const chartData = [...driftHistory].reverse().map((d, i) => ({
    name: `Run ${i + 1}`,
    data_drift: d.data_drift_score,
    prediction_drift: d.prediction_drift_score,
  }));

  if (loading) return <DashboardLayout><Spinner /></DashboardLayout>;

  return (
    <DashboardLayout>
      <div className="flex items-center justify-between mb-8 flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold mb-1">Monitoring</h1>
          <p className="text-muted text-sm">Fairness audits and drift detection for deployed models.</p>
        </div>
        <Select
          options={models.map((m) => ({ value: m.id, label: `${m.name} ${m.version}` }))}
          value={selectedModel || ""}
          onChange={(e) => setSelectedModel(parseInt(e.target.value))}
        />
      </div>

      {!selectedModel ? (
        <Card><EmptyState icon={<Activity size={32} />} title="No models to monitor yet" subtitle="Train a model first in the Models tab." /></Card>
      ) : (
        <>
          <div className="grid lg:grid-cols-2 gap-6">
            <Card>
              <div className="flex items-center justify-between mb-4">
                <h3 className="font-semibold flex items-center gap-2"><Scale size={18} /> Fairness Audit</h3>
                <Button onClick={runFairnessCheck} disabled={running}>{running ? "Running..." : "Run Audit"}</Button>
              </div>
              {fairness.length === 0 && <p className="text-muted text-sm">No fairness audit run yet.</p>}
              <div className="flex flex-col gap-4">
                {fairness.map((f) => (
                  <div key={f.attribute} className="border border-white/10 rounded-xl p-4">
                    <div className="flex items-center justify-between mb-2">
                      <p className="font-medium capitalize">{f.attribute.replaceAll("_", " ")}</p>
                      <Badge status={f.passed ? "passed" : "failed"} />
                    </div>
                    <p className="text-xs text-muted mb-2">
                      Disparate Impact: {f.disparate_impact} (min {f.thresholds_used?.disparate_impact_min ?? 0.8}) ·
                      {" "}Equal Opp. Diff: {f.equal_opportunity_diff} (max {f.thresholds_used?.equal_opportunity_max ?? 0.1})
                    </p>
                    <div className="grid grid-cols-2 gap-2">
                      {Object.entries(f.group_metrics).map(([group, m]) => (
                        <div key={group} className="bg-white/5 rounded-lg p-2 text-xs">
                          <p className="font-medium capitalize">{group}</p>
                          <p className="text-muted">Approval: {(m.approval_rate * 100).toFixed(1)}%</p>
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>

              {mitigations.length > 0 && (
                <div className="mt-4 pt-4 border-t border-white/10">
                  <p className="font-medium mb-3 flex items-center gap-2 text-sm">
                    <Lightbulb size={16} className="text-accent" /> Bias Mitigation Suggestions
                  </p>
                  <div className="space-y-3">
                    {mitigations.map((s, i) => (
                      <div key={i} className="border-l-2 border-accent/40 pl-3">
                        <p className="text-xs uppercase tracking-wide text-accent mb-0.5">
                          {s.attribute} — {s.type.replaceAll("_", " ")}
                        </p>
                        <p className="text-sm">{s.action}</p>
                        <p className="text-muted text-xs mt-0.5">{s.rationale}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </Card>

            <Card>
              <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
                <h3 className="font-semibold flex items-center gap-2"><Activity size={18} /> Drift Detection</h3>
                <div className="flex items-center gap-2">
                  <input
                    type="range" min="0" max="1" step="0.1"
                    value={driftIntensity}
                    onChange={(e) => setDriftIntensity(parseFloat(e.target.value))}
                  />
                  <span className="text-xs text-muted">{driftIntensity}</span>
                  <Button onClick={runDriftCheck} disabled={running}>
                    <RefreshCcw size={14} className="inline mr-1" /> Simulate
                  </Button>
                </div>
              </div>

              {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={220}>
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                    <XAxis dataKey="name" stroke="#7c8b84" fontSize={12} />
                    <YAxis stroke="#7c8b84" fontSize={12} />
                    <Tooltip contentStyle={{ background: "#0e1410", border: "1px solid rgba(34,255,142,0.2)" }} />
                    <Line type="monotone" dataKey="data_drift" stroke="#22ff8e" strokeWidth={2} />
                    <Line type="monotone" dataKey="prediction_drift" stroke="#ffce3c" strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <p className="text-muted text-sm mb-4">No drift checks run yet. Use the slider to simulate a production batch shift.</p>
              )}

              {driftHistory.length > 0 && (
                <div className="mt-4 border-t border-white/10 pt-4">
                  <p className="text-sm mb-2">Latest run:</p>
                  <div className="flex items-center gap-3 flex-wrap">
                    <Badge status={driftHistory[0].drift_detected ? "failed" : "passed"} />
                    {driftHistory[0].retrain_recommended && (
                      <span className="text-xs text-yellow-400">⚠ Retraining recommended</span>
                    )}
                  </div>
                  {driftHistory[0].drifted_features.length > 0 && (
                    <p className="text-xs text-muted mt-2">
                      Drifted features: {driftHistory[0].drifted_features.join(", ")}
                    </p>
                  )}
                </div>
              )}

              {/* Automated Drift Monitoring (Feature 8) */}
              <div className="mt-4 border-t border-white/10 pt-4">
                <p className="text-sm mb-2 flex items-center gap-2"><Clock size={14} /> Scheduled monitoring</p>
                <div className="flex items-center gap-2 flex-wrap">
                  {["off", "daily", "weekly"].map((freq) => (
                    <button
                      key={freq}
                      onClick={() => updateSchedule(freq)}
                      disabled={savingSchedule}
                      className={`px-3 py-1.5 rounded-full text-xs font-medium border transition-colors ${
                        schedule.frequency === freq
                          ? "bg-accent/20 border-accent text-accent"
                          : "border-white/10 text-muted hover:border-white/30"
                      }`}
                    >
                      {freq === "off" ? "Off" : freq === "daily" ? "Daily" : "Weekly"}
                    </button>
                  ))}
                  {schedule.active && schedule.next_run_at && (
                    <span className="text-xs text-muted">
                      Next run: {new Date(schedule.next_run_at).toLocaleString()}
                    </span>
                  )}
                </div>
              </div>
            </Card>
          </div>

          <Card className="mt-6">
            <h3 className="font-semibold mb-4 flex items-center gap-2"><Bell size={18} /> Drift Alerts</h3>
            {alerts.length === 0 ? (
              <EmptyState
                icon={<Bell size={28} />}
                title="No alerts"
                subtitle="You'll see an alert here whenever a manual or scheduled drift check exceeds the threshold."
              />
            ) : (
              <div className="space-y-2">
                {alerts.map((a) => (
                  <div
                    key={a.id}
                    className={`flex items-center justify-between p-3 rounded-xl border text-sm ${
                      a.acknowledged ? "border-white/5 opacity-60" : "border-white/10"
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <Badge status={a.severity} />
                      <span>{a.message}</span>
                    </div>
                    {!a.acknowledged && (
                      <Button variant="ghost" onClick={() => acknowledgeAlert(a.id)}>Acknowledge</Button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Card>

          {/* Automated Retraining Trigger Rules (additive) */}
          <Card className="mt-6">
            <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
              <h3 className="font-semibold flex items-center gap-2">
                <ShieldAlert size={18} /> Retraining Trigger Rules
              </h3>
              <Button onClick={checkRetrainingTriggers} disabled={checkingTriggers}>
                {checkingTriggers ? "Checking..." : "Re-check Triggers"}
              </Button>
            </div>
            <p className="text-muted text-xs mb-4">
              Monitoring rules that recommend retraining when data drift, performance, or fairness conditions are violated.
            </p>

            {!retrainingTriggers ? (
              <p className="text-muted text-sm">No trigger evaluation yet.</p>
            ) : (
              <>
                {retrainingTriggers.any_triggered && (
                  <div className="mb-4 p-3 rounded-xl bg-red-400/10 border border-red-400/30 text-sm text-red-400">
                    ⚠ Retraining recommended for {retrainingTriggers.model_name} {retrainingTriggers.model_version}
                  </div>
                )}
                <div className="space-y-3">
                  {retrainingTriggers.triggers.map((t) => (
                    <div
                      key={t.trigger_name}
                      className={`border rounded-xl p-4 ${
                        t.triggered ? "border-red-400/30 bg-red-400/5" : "border-white/10"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2 flex-wrap gap-2">
                        <p className="font-medium text-sm">{t.trigger_name}</p>
                        <Badge status={t.triggered ? "failed" : t.data_available ? "passed" : "pending"} />
                      </div>
                      <p className="text-xs text-muted">{t.reason}</p>
                      {t.triggered && t.recommendation && (
                        <p className="text-xs text-red-400 mt-1.5">{t.recommendation}</p>
                      )}
                    </div>
                  ))}
                </div>
              </>
            )}
          </Card>
        </>
      )}
    </DashboardLayout>
  );
}
