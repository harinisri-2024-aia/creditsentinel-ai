import React, { useEffect, useState } from "react";
import { Users, X, ArrowUpRight, ArrowDownRight } from "lucide-react";
import { DashboardLayout } from "../components/Layout";
import { Card, Badge, Spinner, EmptyState } from "../components/UI";
import { applicantsApi } from "../services/api";

function ShapMini({ contributions }) {
  if (!contributions || contributions.length === 0) {
    return <p className="text-muted text-xs">No explanation available for this prediction.</p>;
  }
  const maxAbs = Math.max(...contributions.map((c) => Math.abs(c.contribution)), 1);
  return (
    <div className="space-y-2.5">
      {contributions.map((c, i) => {
        const widthPct = (Math.abs(c.contribution) / maxAbs) * 100;
        const isRiskUp = c.direction === "risk_up";
        return (
          <div key={i} className="text-xs">
            <div className="flex items-center justify-between mb-1">
              <span className="text-muted capitalize flex items-center gap-1">
                {isRiskUp ? <ArrowUpRight size={12} className="text-red-400" /> : <ArrowDownRight size={12} className="text-accent" />}
                {c.feature.replaceAll("_", " ")} = {c.value}
              </span>
              <span className={isRiskUp ? "text-red-400" : "text-accent"}>
                {isRiskUp ? "+" : ""}{c.contribution} pts
              </span>
            </div>
            <div className="w-full h-2 rounded-full bg-white/5 overflow-hidden">
              <div className={`h-full rounded-full ${isRiskUp ? "bg-red-400/80" : "bg-accent/80"}`} style={{ width: `${widthPct}%` }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function ApplicantsPage() {
  const [applicants, setApplicants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);

  useEffect(() => {
    applicantsApi.list().then((res) => setApplicants(res.data)).finally(() => setLoading(false));
  }, []);

  const openApplicant = async (id) => {
    setSelected(id);
    setDetailLoading(true);
    setDetail(null);
    try {
      const res = await applicantsApi.get(id);
      setDetail(res.data);
    } finally {
      setDetailLoading(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1">Applicant Management</h1>
        <p className="text-muted text-sm">Every loan application scored by your models — click a row for the full explanation.</p>
      </div>

      <Card>
        {loading ? (
          <Spinner />
        ) : applicants.length === 0 ? (
          <EmptyState
            icon={<Users size={32} />}
            title="No applications yet"
            subtitle="Run a prediction from the Models tab to see applicants appear here."
          />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-muted text-left border-b border-white/10">
                  <th className="py-2 pr-4">Application ID</th>
                  <th className="py-2 pr-4">Applicant Name</th>
                  <th className="py-2 pr-4">Risk Score</th>
                  <th className="py-2 pr-4">Prediction</th>
                  <th className="py-2 pr-4">Decision</th>
                  <th className="py-2 pr-4">Model Version Used</th>
                  <th className="py-2 pr-4">Date</th>
                </tr>
              </thead>
              <tbody>
                {applicants.map((a) => (
                  <tr
                    key={a.application_id}
                    onClick={() => openApplicant(a.application_id)}
                    className="border-b border-white/5 cursor-pointer hover:bg-white/5 transition"
                  >
                    <td className="py-3 pr-4 text-muted">#{String(a.application_id).padStart(3, "0")}</td>
                    <td className="py-3 pr-4">{a.applicant_name}</td>
                    <td className="py-3 pr-4">{a.risk_score}</td>
                    <td className="py-3 pr-4">
                      <Badge status={a.decision === "Approved" ? "approve" : "decline"} />
                    </td>
                    <td className="py-3 pr-4">{a.decision}</td>
                    <td className="py-3 pr-4 text-muted">{a.model_version_used}</td>
                    <td className="py-3 pr-4 text-muted">{a.date ? new Date(a.date).toLocaleDateString() : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {selected && (
        <div className="fixed inset-0 z-50 flex items-stretch justify-end bg-black/50" onClick={() => setSelected(null)}>
          <div
            className="w-full max-w-md bg-bg glass m-4 rounded-2xl p-6 overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-6">
              <h3 className="font-semibold text-lg">Application #{String(selected).padStart(3, "0")}</h3>
              <button onClick={() => setSelected(null)} className="text-muted hover:text-white">
                <X size={20} />
              </button>
            </div>

            {detailLoading || !detail ? (
              <Spinner />
            ) : (
              <div className="space-y-5">
                <div>
                  <p className="text-muted text-xs uppercase tracking-wide mb-1">Applicant</p>
                  <p className="font-medium">{detail.applicant_name}</p>
                </div>

                <div className="flex items-center gap-4">
                  <div>
                    <p className="text-muted text-xs uppercase tracking-wide mb-1">Risk Score</p>
                    <p className="text-2xl font-bold text-accent">{detail.risk_score}<span className="text-sm text-muted">/100</span></p>
                  </div>
                  <div>
                    <p className="text-muted text-xs uppercase tracking-wide mb-1">Decision</p>
                    <Badge status={detail.decision === "Approved" ? "approve" : "decline"} />
                  </div>
                </div>

                <div>
                  <p className="text-muted text-xs uppercase tracking-wide mb-1">Model Version Used</p>
                  <p className="text-sm">{detail.model_version_used}</p>
                </div>

                <div className="pt-4 border-t border-white/10">
                  <p className="text-muted text-xs uppercase tracking-wide mb-3">Explanation — factors affecting decision</p>
                  <ShapMini contributions={detail.shap_explanation} />
                </div>

                {detail.counterfactuals && detail.counterfactuals.length > 0 && (
                  <div className="pt-4 border-t border-white/10">
                    <p className="text-muted text-xs uppercase tracking-wide mb-2">What would change this decision</p>
                    {detail.counterfactuals.map((c, i) => (
                      <p key={i} className="text-xs mb-1">{c.hint}</p>
                    ))}
                  </div>
                )}

                <div className="pt-4 border-t border-white/10">
                  <p className="text-muted text-xs uppercase tracking-wide mb-2">Submitted Application Data</p>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    {Object.entries(detail.input_payload || {}).map(([k, v]) => (
                      <div key={k} className="bg-white/5 rounded-lg p-2">
                        <p className="text-muted capitalize">{k.replaceAll("_", " ")}</p>
                        <p>{v}</p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </DashboardLayout>
  );
}
