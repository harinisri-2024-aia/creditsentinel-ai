import React, { useEffect, useState } from "react";
import { Cpu, PlayCircle, Sparkles, FileDown, Lightbulb, ArrowUpRight, ArrowDownRight } from "lucide-react";
import { DashboardLayout } from "../components/Layout";
import { Card, Button, Select, Input, Badge, Spinner, EmptyState } from "../components/UI";
import { modelsApi, governanceApi, datasetsApi, reportsApi } from "../services/api";
import { useAuth } from "../context/AuthContext";

const initialForm = {
  age: 35, annual_income: 60000, credit_score: 700, loan_amount: 15000,
  loan_term_months: 36, existing_debt: 5000, employment_years: 8, num_credit_lines: 4,
};

// Display labels for every algorithm selectable in "Train New Model" — kept
// in one place so the dropdown and the Model Versions table column always
// agree (additive: the two original algorithms plus Logistic Regression and
// Decision Tree).
const ALGORITHM_LABELS = {
  xgboost: "XGBoost",
  random_forest: "Random Forest",
  logistic_regression: "Logistic Regression",
  decision_tree: "Decision Tree",
};

// SHAP-style signed contribution bar chart (Feature 3: Explainable AI Upgrade).
// Positive bars push risk UP (toward decline), negative bars push risk DOWN
// (toward approve) — mirrors how a real SHAP force/waterfall plot reads.
function ShapChart({ contributions }) {
  if (!contributions || contributions.length === 0) return null;
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
                {isRiskUp ? (
                  <ArrowUpRight size={12} className="text-red-400" />
                ) : (
                  <ArrowDownRight size={12} className="text-accent" />
                )}
                {c.feature.replaceAll("_", " ")}
              </span>
              <span className={isRiskUp ? "text-red-400" : "text-accent"}>
                {isRiskUp ? "+" : ""}{c.contribution} pts
              </span>
            </div>
            <div className="w-full h-2 rounded-full bg-white/5 overflow-hidden flex">
              {/* Bar grows from center-left for risk_down, center-right for risk_up to visually echo a force plot */}
              <div
                className={`h-full rounded-full ${isRiskUp ? "bg-red-400/80" : "bg-accent/80"}`}
                style={{ width: `${widthPct}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// SHAP waterfall chart (additive): visualizes the same signed contributions
// as ShapChart above, but as a cumulative waterfall — starting from the
// model's average ("expected") risk score, stepping through each feature's
// contribution in order of impact, and landing on this prediction's final
// risk score. This is the classic shap.plots.waterfall layout, reusing the
// existing color/icon language (red = risk up, accent green = risk down).
function ShapWaterfallChart({ waterfall }) {
  if (!waterfall || !waterfall.steps || waterfall.steps.length === 0) return null;

  const allValues = waterfall.steps.flatMap((s) => [s.start, s.end]);
  const lo = Math.min(waterfall.expected_value, waterfall.final_value, ...allValues);
  const hi = Math.max(waterfall.expected_value, waterfall.final_value, ...allValues);
  const range = Math.max(hi - lo, 1);
  const toPct = (v) => ((v - lo) / range) * 100;

  return (
    <div>
      <div className="flex items-center justify-between text-xs text-muted mb-3">
        <span>Expected risk (avg. applicant): <span className="text-white">{waterfall.expected_value}</span></span>
        <span>Final risk score: <span className="text-white">{waterfall.final_value}</span></span>
      </div>
      <div className="space-y-2.5">
        {waterfall.steps.map((s, i) => {
          const isRiskUp = s.direction === "risk_up";
          const isNeutral = s.direction === "neutral";
          const left = Math.min(toPct(s.start), toPct(s.end));
          const width = Math.max(Math.abs(toPct(s.end) - toPct(s.start)), 1);
          return (
            <div key={i} className="text-xs">
              <div className="flex items-center justify-between mb-1">
                <span className="text-muted flex items-center gap-1">
                  {isNeutral ? null : isRiskUp ? (
                    <ArrowUpRight size={12} className="text-red-400" />
                  ) : (
                    <ArrowDownRight size={12} className="text-accent" />
                  )}
                  {s.label}
                  {s.value !== null && s.value !== undefined && (
                    <span className="text-muted/70">({Math.round(s.value * 100) / 100})</span>
                  )}
                </span>
                <span className={isRiskUp ? "text-red-400" : isNeutral ? "text-muted" : "text-accent"}>
                  {s.contribution > 0 ? "+" : ""}{s.contribution} pts
                </span>
              </div>
              <div className="w-full h-2 rounded-full bg-white/5 overflow-hidden relative">
                <div
                  className={`h-full rounded-full absolute top-0 ${
                    isRiskUp ? "bg-red-400/80" : isNeutral ? "bg-white/15" : "bg-accent/80"
                  }`}
                  style={{ left: `${left}%`, width: `${width}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function ModelsPage() {
  const { hasRole } = useAuth();
  const [models, setModels] = useState([]);
  const [datasets, setDatasets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [training, setTraining] = useState(false);
  const [algorithm, setAlgorithm] = useState("xgboost");
  const [datasetId, setDatasetId] = useState("");
  const [selectedModel, setSelectedModel] = useState(null);
  const [form, setForm] = useState(initialForm);
  const [applicantName, setApplicantName] = useState("");
  const [predictResult, setPredictResult] = useState(null);
  const [predicting, setPredicting] = useState(false);
  const [governing, setGoverning] = useState(false);
  const [governanceResult, setGovernanceResult] = useState(null);
  const [mitigations, setMitigations] = useState([]);
  const [exporting, setExporting] = useState(false);

  const canTrain = hasRole("data_scientist");

  const loadModels = () => {
    setLoading(true);
    modelsApi.list().then((res) => {
      setModels(res.data);
      if (res.data.length && !selectedModel) setSelectedModel(res.data[0].id);
    }).finally(() => setLoading(false));
  };

  const loadDatasets = () => {
    datasetsApi.list().then((res) => setDatasets(res.data.filter((d) => d.validation_status === "valid")));
  };

  useEffect(() => { loadModels(); loadDatasets(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleTrain = async () => {
    setTraining(true);
    try {
      await modelsApi.train({
        name: "credit-risk-model",
        algorithm,
        dataset_id: datasetId ? parseInt(datasetId, 10) : null,
      });
      loadModels();
    } finally {
      setTraining(false);
    }
  };

  const handlePredict = async () => {
    if (!selectedModel) return;
    setPredicting(true);
    setPredictResult(null);
    try {
      const res = await modelsApi.predict({
        model_id: selectedModel,
        applicant_name: applicantName || "Unnamed Applicant",
        ...form,
      });
      setPredictResult(res.data);
    } catch (e) {
      setPredictResult({ error: e?.response?.data?.detail || "Prediction failed" });
    } finally {
      setPredicting(false);
    }
  };

  const runFullGovernance = async () => {
    if (!selectedModel) return;
    setGoverning(true);
    setGovernanceResult(null);
    setMitigations([]);
    try {
      const fairnessRes = await governanceApi.runFairness(selectedModel);
      setMitigations(fairnessRes.data.mitigation_suggestions || []);
      const decision = await governanceApi.decide(selectedModel);
      setGovernanceResult(decision.data);
      loadModels();
    } finally {
      setGoverning(false);
    }
  };

  const handleExport = async (format) => {
    if (!selectedModel) return;
    setExporting(true);
    try {
      await reportsApi.download(selectedModel, format);
    } finally {
      setExporting(false);
    }
  };

  return (
    <DashboardLayout>
      <div className="flex items-center justify-between mb-8 flex-wrap gap-4">
        <div>
          <h1 className="text-2xl font-bold mb-1">Models</h1>
          <p className="text-muted text-sm">Train, evaluate, and govern credit risk model versions.</p>
        </div>
        {canTrain && (
          <div className="flex items-center gap-3 flex-wrap">
            <Select
              options={[
                { value: "", label: "Synthetic dataset (default)" },
                ...datasets.map((d) => ({ value: String(d.id), label: `${d.filename} (${d.row_count} rows)` })),
              ]}
              value={datasetId}
              onChange={(e) => setDatasetId(e.target.value)}
            />
            <Select
              options={Object.entries(ALGORITHM_LABELS).map(([value, label]) => ({ value, label }))}
              value={algorithm}
              onChange={(e) => setAlgorithm(e.target.value)}
            />
            <Button onClick={handleTrain} disabled={training}>
              {training ? "Training..." : <><Sparkles size={16} className="inline mr-1" /> Train New Model</>}
            </Button>
          </div>
        )}
      </div>

      {loading ? <Spinner /> : (
        <div className="grid lg:grid-cols-3 gap-6">
          <Card className="lg:col-span-2">
            <h3 className="font-semibold mb-4 flex items-center gap-2"><Cpu size={18} /> Model Versions</h3>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-muted text-left border-b border-white/10">
                    <th className="py-2 pr-4">Select</th>
                    <th className="py-2 pr-4">Version</th>
                    <th className="py-2 pr-4">Algorithm</th>
                    <th className="py-2 pr-4">Acc.</th>
                    <th className="py-2 pr-4">F1</th>
                    <th className="py-2 pr-4">Status</th>
                    <th className="py-2 pr-4">Governance</th>
                  </tr>
                </thead>
                <tbody>
                  {models.map((m) => (
                    <tr key={m.id} className="border-b border-white/5">
                      <td className="py-3 pr-4">
                        <input type="radio" checked={selectedModel === m.id} onChange={() => setSelectedModel(m.id)} />
                      </td>
                      <td className="py-3 pr-4">{m.name} {m.version}</td>
                      <td className="py-3 pr-4 text-muted">{ALGORITHM_LABELS[m.algorithm] || m.algorithm}</td>
                      <td className="py-3 pr-4">{(m.accuracy * 100).toFixed(1)}%</td>
                      <td className="py-3 pr-4">{(m.f1 * 100).toFixed(1)}%</td>
                      <td className="py-3 pr-4"><Badge status={m.status} /></td>
                      <td className="py-3 pr-4"><Badge status={m.governance_decision} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {models.length === 0 && (
                <EmptyState
                  icon={<Cpu size={32} />}
                  title="No models yet"
                  subtitle={canTrain ? "Train your first credit risk model to get started." : "Ask a Data Scientist on your team to train a model."}
                />
              )}
            </div>

            {models.length > 0 && (
              <div className="mt-6 flex items-center gap-3 flex-wrap">
                <Button onClick={runFullGovernance} disabled={!selectedModel || governing}>
                  {governing ? "Evaluating gates..." : "Run Fairness Audit + Governance Decision"}
                </Button>
                <Button variant="ghost" onClick={() => handleExport("pdf")} disabled={!selectedModel || exporting}>
                  <FileDown size={16} className="inline mr-1" /> {exporting ? "Exporting..." : "Export PDF"}
                </Button>
                <Button variant="ghost" onClick={() => handleExport("csv")} disabled={!selectedModel || exporting}>
                  <FileDown size={16} className="inline mr-1" /> Export CSV
                </Button>
              </div>
            )}

            {governanceResult && (
              <div className="mt-4 p-4 rounded-xl bg-white/5 text-sm">
                <p className="font-medium mb-1">
                  Decision: <Badge status={governanceResult.decision} />
                </p>
                <p className="text-muted">{governanceResult.reason}</p>
              </div>
            )}

            {mitigations.length > 0 && (
              <div className="mt-4 p-4 rounded-xl bg-white/5 text-sm">
                <p className="font-medium mb-3 flex items-center gap-2">
                  <Lightbulb size={16} className="text-accent" /> Bias Mitigation Suggestions
                </p>
                <div className="space-y-3">
                  {mitigations.map((s, i) => (
                    <div key={i} className="border-l-2 border-accent/40 pl-3">
                      <p className="font-medium text-xs uppercase tracking-wide text-accent mb-0.5">
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
            <h3 className="font-semibold mb-4 flex items-center gap-2"><PlayCircle size={18} /> Try a Prediction</h3>
            <Input
              label="applicant name"
              type="text"
              value={applicantName}
              onChange={(e) => setApplicantName(e.target.value)}
              placeholder="e.g. Jane Doe"
            />
            <div className="grid grid-cols-2 gap-2">
              {Object.keys(form).map((key) => (
                <Input
                  key={key}
                  label={key.replaceAll("_", " ")}
                  type="number"
                  value={form[key]}
                  onChange={(e) => setForm({ ...form, [key]: parseFloat(e.target.value) || 0 })}
                />
              ))}
            </div>
            <Button className="w-full mt-2" onClick={handlePredict} disabled={!selectedModel || predicting}>
              {predicting ? "Scoring..." : "Get Risk Score"}
            </Button>

            {predictResult && !predictResult.error && (
              <div className="mt-4 p-4 rounded-xl bg-white/5 text-sm">
                <p className="font-medium mb-1">
                  Risk Score: <span className="text-accent">{predictResult.risk_score}</span> /100
                  <span className="text-muted text-xs"> (lower = safer)</span>
                </p>
                <p className="mb-3">
                  Decision: <span className={predictResult.decision === "APPROVE" ? "text-accent" : "text-red-400"}>
                    {predictResult.decision}
                  </span>
                </p>

                <p className="text-muted mb-2 text-xs uppercase tracking-wide">SHAP-style explanation</p>
                <ShapChart contributions={predictResult.shap_explanation} />

                {predictResult.shap_waterfall && (
                  <div className="mt-4 pt-3 border-t border-white/10">
                    <p className="text-muted mb-2 text-xs uppercase tracking-wide">SHAP waterfall — feature contribution</p>
                    <ShapWaterfallChart waterfall={predictResult.shap_waterfall} />
                  </div>
                )}

                {predictResult.counterfactuals && predictResult.counterfactuals.length > 0 && (
                  <div className="mt-4 pt-3 border-t border-white/10">
                    <p className="text-muted mb-2 text-xs uppercase tracking-wide">What would change this decision</p>
                    {predictResult.counterfactuals.map((c, i) => (
                      <p key={i} className="text-xs mb-1">{c.hint}</p>
                    ))}
                  </div>
                )}
              </div>
            )}
            {predictResult?.error && <p className="text-red-400 text-sm mt-3">{predictResult.error}</p>}
          </Card>
        </div>
      )}
    </DashboardLayout>
  );
}
