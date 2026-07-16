import React from "react";
import { motion } from "framer-motion";

export function Card({ children, className = "", hover = true }) {
  return (
    <div className={`glass ${hover ? "glass-hover" : ""} p-6 ${className}`}>
      {children}
    </div>
  );
}

export function Badge({ status }) {
  const map = {
    passed: { cls: "badge-pass", label: "PASSED" },
    approved: { cls: "badge-pass", label: "APPROVED" },
    production: { cls: "badge-pass", label: "PRODUCTION" },
    approve: { cls: "badge-pass", label: "APPROVE" },
    valid: { cls: "badge-pass", label: "VALID" },
    active: { cls: "badge-pass", label: "ACTIVE" },
    failed: { cls: "badge-fail", label: "FAILED" },
    rejected: { cls: "badge-fail", label: "REJECTED" },
    decline: { cls: "badge-fail", label: "DECLINE" },
    invalid: { cls: "badge-fail", label: "INVALID" },
    critical: { cls: "badge-fail", label: "CRITICAL" },
    pending: { cls: "badge-pending", label: "PENDING" },
    evaluated: { cls: "badge-pending", label: "EVALUATED" },
    training: { cls: "badge-pending", label: "TRAINING" },
    warning: { cls: "badge-pending", label: "WARNING" },
    off: { cls: "badge-pending", label: "OFF" },
  };
  const key = status?.toLowerCase?.() || status;
  const conf = map[key] || { cls: "badge-pending", label: status?.toUpperCase?.() || "—" };
  return (
    <span className={`px-3 py-1 rounded-full text-xs font-semibold tracking-wide ${conf.cls}`}>
      {conf.label}
    </span>
  );
}

export function StatCard({ label, value, suffix = "", icon, accentColor = "text-accent" }) {
  return (
    <Card className="flex items-center justify-between">
      <div>
        <p className="text-muted text-sm mb-1">{label}</p>
        <p className={`text-3xl font-bold ${accentColor}`}>
          {value}
          <span className="text-base font-medium text-muted">{suffix}</span>
        </p>
      </div>
      {icon && <div className="text-accent opacity-80">{icon}</div>}
    </Card>
  );
}

export function Button({ children, variant = "primary", className = "", ...props }) {
  const cls = variant === "primary" ? "btn-primary" : "btn-ghost";
  return (
    <motion.button
      whileTap={{ scale: 0.97 }}
      className={`${cls} ${className} font-medium text-sm`}
      {...props}
    >
      {children}
    </motion.button>
  );
}

export function Input({ label, ...props }) {
  return (
    <div className="mb-4">
      {label && <label className="block text-sm text-muted mb-1.5">{label}</label>}
      <input className="input-field" {...props} />
    </div>
  );
}

export function Select({ label, options, ...props }) {
  return (
    <div className="mb-4">
      {label && <label className="block text-sm text-muted mb-1.5">{label}</label>}
      <select className="input-field" {...props}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function SectionHeading({ kicker, title, subtitle }) {
  return (
    <div className="mb-10 text-center max-w-2xl mx-auto">
      {kicker && (
        <p className="text-accent text-sm font-semibold tracking-widest uppercase mb-3">
          {kicker}
        </p>
      )}
      <h2 className="text-3xl md:text-4xl font-bold mb-3">{title}</h2>
      {subtitle && <p className="text-muted">{subtitle}</p>}
    </div>
  );
}

export function Spinner() {
  return (
    <div className="flex items-center justify-center py-10">
      <div className="w-8 h-8 border-2 border-accent/30 border-t-accent rounded-full animate-spin" />
    </div>
  );
}

// New: shared empty-state for lists with no data yet (datasets, alerts,
// applicants, comparisons before selection, etc.) so every new feature has a
// consistent, polished "nothing here yet" treatment instead of a blank div.
export function EmptyState({ icon, title, subtitle, action }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-14 px-6">
      {icon && <div className="text-accent/60 mb-4">{icon}</div>}
      <p className="font-semibold text-lg mb-1">{title}</p>
      {subtitle && <p className="text-muted text-sm max-w-sm">{subtitle}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

// New: small horizontal progress/score bar used by SHAP-style contribution
// charts, drift gauges, and upload progress.
export function ProgressBar({ value, max = 100, colorClass = "bg-accent" }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  return (
    <div className="w-full h-2 rounded-full bg-white/5 overflow-hidden">
      <motion.div
        className={`h-full rounded-full ${colorClass}`}
        initial={{ width: 0 }}
        animate={{ width: `${pct}%` }}
        transition={{ duration: 0.6, ease: "easeOut" }}
      />
    </div>
  );
}

// New: skeleton placeholder for loading states (Feature 10: loading/empty states polish)
export function Skeleton({ className = "" }) {
  return <div className={`animate-pulse rounded-lg bg-white/5 ${className}`} />;
}
