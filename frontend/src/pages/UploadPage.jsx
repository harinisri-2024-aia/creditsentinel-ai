import React, { useEffect, useRef, useState } from "react";
import { UploadCloud, FileSpreadsheet, CheckCircle2, XCircle, Trash2 } from "lucide-react";
import { DashboardLayout } from "../components/Layout";
import { Card, Badge, Spinner, EmptyState } from "../components/UI";
import { datasetsApi } from "../services/api";

export default function UploadPage() {
  const [schema, setSchema] = useState(null);
  const [datasets, setDatasets] = useState([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [lastResult, setLastResult] = useState(null);
  const fileInputRef = useRef(null);

  const loadDatasets = () => {
    datasetsApi.list().then((res) => setDatasets(res.data)).finally(() => setLoading(false));
  };

  useEffect(() => {
    datasetsApi.requiredSchema().then((res) => setSchema(res.data));
    loadDatasets();
  }, []);

  const handleFileChange = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setProgress(0);
    setLastResult(null);
    try {
      const res = await datasetsApi.upload(file, (evt) => {
        if (evt.total) setProgress(Math.round((evt.loaded / evt.total) * 100));
      });
      setLastResult(res.data);
      loadDatasets();
    } catch (err) {
      setLastResult({ validation_status: "invalid", validation_message: err?.response?.data?.detail || "Upload failed." });
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDelete = async (id) => {
    await datasetsApi.remove(id);
    loadDatasets();
  };

  return (
    <DashboardLayout>
      <div className="mb-8">
        <h1 className="text-2xl font-bold mb-1">Dataset Upload &amp; Training Pipeline</h1>
        <p className="text-muted text-sm">
          Upload Dataset → Validate columns → Train ML model → Evaluate performance → Run fairness check → Register model version.
        </p>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <h3 className="font-semibold mb-4 flex items-center gap-2"><UploadCloud size={18} /> Upload a dataset</h3>

          <label
            htmlFor="dataset-upload-input"
            className="flex flex-col items-center justify-center border-2 border-dashed border-white/15 rounded-2xl py-12 cursor-pointer hover:border-accent/50 transition"
          >
            <UploadCloud size={32} className="text-accent mb-3" />
            <p className="font-medium mb-1">Click to choose a CSV or XLSX file</p>
            <p className="text-muted text-xs">Max 25MB</p>
            <input
              id="dataset-upload-input"
              ref={fileInputRef}
              type="file"
              accept=".csv,.xlsx,.xls"
              className="hidden"
              onChange={handleFileChange}
              disabled={uploading}
            />
          </label>

          {uploading && (
            <div className="mt-4">
              <div className="w-full h-2 rounded-full bg-white/5 overflow-hidden">
                <div className="h-full bg-accent rounded-full transition-all" style={{ width: `${progress}%` }} />
              </div>
              <p className="text-xs text-muted mt-1">Uploading & validating... {progress}%</p>
            </div>
          )}

          {lastResult && (
            <div className={`mt-4 p-4 rounded-xl text-sm flex items-start gap-3 ${
              lastResult.validation_status === "valid" ? "bg-accent/10 border border-accent/30" : "bg-red-500/10 border border-red-500/30"
            }`}>
              {lastResult.validation_status === "valid" ? (
                <CheckCircle2 size={18} className="text-accent mt-0.5" />
              ) : (
                <XCircle size={18} className="text-red-400 mt-0.5" />
              )}
              <div>
                <p className="font-medium">{lastResult.validation_status === "valid" ? "Dataset validated successfully" : "Validation failed"}</p>
                <p className="text-muted text-xs mt-0.5">{lastResult.validation_message}</p>
                {lastResult.row_count != null && <p className="text-xs mt-1">{lastResult.row_count} rows detected.</p>}
              </div>
            </div>
          )}

          <div className="mt-8">
            <h4 className="font-medium mb-3 text-sm">Your uploaded datasets</h4>
            {loading ? (
              <Spinner />
            ) : datasets.length === 0 ? (
              <EmptyState icon={<FileSpreadsheet size={28} />} title="No datasets uploaded yet" />
            ) : (
              <div className="space-y-2">
                {datasets.map((d) => (
                  <div key={d.id} className="flex items-center justify-between p-3 rounded-xl border border-white/10 text-sm">
                    <div className="flex items-center gap-3">
                      <FileSpreadsheet size={16} className="text-muted" />
                      <div>
                        <p className="font-medium">{d.filename}</p>
                        <p className="text-muted text-xs">{d.row_count} rows · {new Date(d.created_at).toLocaleDateString()}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3">
                      <Badge status={d.validation_status} />
                      <button onClick={() => handleDelete(d.id)} className="text-muted hover:text-red-400">
                        <Trash2 size={16} />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Card>

        <Card>
          <h3 className="font-semibold mb-4">Required schema</h3>
          {!schema ? (
            <Spinner />
          ) : (
            <div className="space-y-4 text-sm">
              <div>
                <p className="text-muted text-xs uppercase tracking-wide mb-1">Feature columns (numeric)</p>
                <p>{schema.feature_columns.join(", ")}</p>
              </div>
              <div>
                <p className="text-muted text-xs uppercase tracking-wide mb-1">Sensitive attributes (for fairness)</p>
                <p>{schema.sensitive_columns.join(", ")}</p>
              </div>
              <div>
                <p className="text-muted text-xs uppercase tracking-wide mb-1">Target column</p>
                <p>{schema.target_column}</p>
              </div>
              <p className="text-muted text-xs pt-2 border-t border-white/10">{schema.notes}</p>
            </div>
          )}
        </Card>
      </div>
    </DashboardLayout>
  );
}
