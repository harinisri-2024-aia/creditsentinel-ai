import React, { useEffect, useState } from "react";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { Cpu, ShieldCheck, AlertTriangle, Activity, BarChart3, FileClock } from "lucide-react";
import { DashboardLayout } from "../components/Layout";
import { Card, StatCard, Badge, Spinner, EmptyState } from "../components/UI";
import { modelsApi, governanceApi } from "../services/api";

export default function DashboardPage() {
  const [models, setModels] = useState([]);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([modelsApi.list(), governanceApi.auditLogs()])
      .then(([mRes, lRes]) => {
        setModels(mRes.data);
        setLogs(lRes.data);
      })
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <DashboardLayout><Spinner /></DashboardLayout>;

  const totalModels = models.length;
  const approved = models.filter((m) => m.governance_decision === "approved").length;
  const rejected = models.filter((m) => m.governance_decision === "rejected").length;
  const avgAccuracy = totalModels
    ? ((models.reduce((s, m) => s + m.accuracy, 0) / totalModels) * 100).toFixed(1)
    : "0.0";

  const chartData = models.slice(0, 8).map((m) => ({
    name: `${m.name.split("-")[0]} ${m.version}`,
    accuracy: +(m.accuracy * 100).toFixed(1),
    f1: +(m.f1 * 100).toFixed(1),
  }));

  return (
    <DashboardLayout>
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1">Governance Overview</h1>
        <p className="text-muted text-sm">Live snapshot of model health, fairness, and deployment status.</p>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5 mb-8">
        <StatCard label="Total Models" value={totalModels} icon={<Cpu size={24} />} />
        <StatCard label="Approved" value={approved} icon={<ShieldCheck size={24} />} />
        <StatCard label="Rejected" value={rejected} icon={<AlertTriangle size={24} />} accentColor="text-red-400" />
        <StatCard label="Avg. Accuracy" value={avgAccuracy} suffix="%" icon={<Activity size={24} />} />
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <h3 className="font-semibold mb-4">Model Performance Comparison</h3>
          {chartData.length === 0 ? (
            <EmptyState
              icon={<BarChart3 size={28} />}
              title="No models trained yet"
              subtitle="Head to the Models tab to train your first credit risk model."
            />
          ) : (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="name" stroke="#7c8b84" fontSize={12} />
                <YAxis stroke="#7c8b84" fontSize={12} />
                <Tooltip contentStyle={{ background: "#0e1410", border: "1px solid rgba(34,255,142,0.2)" }} />
                <Bar dataKey="accuracy" fill="#22ff8e" radius={[6, 6, 0, 0]} />
                <Bar dataKey="f1" fill="#0fae66" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </Card>

        <Card>
          <h3 className="font-semibold mb-4">Recent Audit Logs</h3>
          <div className="flex flex-col gap-3 max-h-80 overflow-y-auto">
            {logs.length === 0 ? (
              <EmptyState icon={<FileClock size={28} />} title="No activity yet" />
            ) : (
              logs.slice(0, 10).map((log) => (
                <div key={log.id} className="border-b border-white/5 pb-2">
                  <p className="text-sm font-medium">{log.action.replaceAll("_", " ")}</p>
                  <p className="text-xs text-muted">{log.details}</p>
                </div>
              ))
            )}
          </div>
        </Card>
      </div>

      <Card className="mt-6">
        <h3 className="font-semibold mb-4">Model Registry</h3>
        {models.length === 0 ? (
          <EmptyState icon={<Cpu size={28} />} title="No models in your registry yet" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-muted text-left border-b border-white/10">
                  <th className="py-2 pr-4">Name</th>
                  <th className="py-2 pr-4">Version</th>
                  <th className="py-2 pr-4">Algorithm</th>
                  <th className="py-2 pr-4">Accuracy</th>
                  <th className="py-2 pr-4">Fairness</th>
                  <th className="py-2 pr-4">Governance</th>
                </tr>
              </thead>
              <tbody>
                {models.map((m) => (
                  <tr key={m.id} className="border-b border-white/5">
                    <td className="py-3 pr-4">{m.name}</td>
                    <td className="py-3 pr-4">{m.version}</td>
                    <td className="py-3 pr-4 uppercase text-muted">{m.algorithm}</td>
                    <td className="py-3 pr-4">{(m.accuracy * 100).toFixed(1)}%</td>
                    <td className="py-3 pr-4"><Badge status={m.fairness_status} /></td>
                    <td className="py-3 pr-4"><Badge status={m.governance_decision} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </DashboardLayout>
  );
}
