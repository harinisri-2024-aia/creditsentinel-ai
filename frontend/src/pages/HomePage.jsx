import React from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import {
  Shield, AlertTriangle, Eye, GitBranch, Scale, RefreshCcw,
  CheckCircle2, XCircle, ArrowRight, Database, Cpu, Activity, Lock,
} from "lucide-react";
import { PublicNav } from "../components/Layout";
import { Card, SectionHeading, Button } from "../components/UI";

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5 } },
};

export default function HomePage() {
  const navigate = useNavigate();

  return (
    <div className="bg-bg min-h-screen overflow-x-hidden">
      <PublicNav />

      {/* Hero */}
      <section className="relative pt-44 pb-28 px-6">
        <div className="absolute inset-0 -z-10 opacity-30" style={{
          background: "radial-gradient(circle at 50% 0%, rgba(34,255,142,0.15), transparent 60%)",
        }} />
        <div className="max-w-5xl mx-auto text-center">
          <motion.div initial="hidden" animate="show" variants={fadeUp}
            className="inline-flex items-center gap-2 glass px-4 py-2 mb-8 text-sm text-accent">
            <Shield size={16} /> Responsible ML Governance for Lending
          </motion.div>
          <motion.h1 initial="hidden" animate="show" variants={fadeUp}
            className="text-4xl md:text-6xl font-extrabold leading-tight mb-6">
            A monitoring shield for <span className="gradient-text">smarter and fairer</span> lending models.
          </motion.h1>
          <motion.p initial="hidden" animate="show" variants={fadeUp}
            className="text-muted text-lg max-w-2xl mx-auto mb-10">
            CreditSentinel continuously monitors credit risk models for performance decay, hidden bias,
            and data drift — then automatically governs which models are safe to deploy.
          </motion.p>
          <motion.div initial="hidden" animate="show" variants={fadeUp}
            className="flex items-center justify-center gap-4">
            <Button onClick={() => navigate("/register")}>
              Launch Platform <ArrowRight className="inline ml-1" size={16} />
            </Button>
            <Button variant="ghost" onClick={() => navigate("/login")}>Log in</Button>
          </motion.div>
        </div>
      </section>

      {/* Problem */}
      <section id="problem" className="px-6 py-24">
        <div className="max-w-6xl mx-auto">
          <SectionHeading
            kicker="The Problem"
            title="Traditional credit scoring is built to fail silently"
            subtitle="Most lending systems optimize for accuracy at training time — and then stop looking."
          />
          <div className="grid md:grid-cols-3 gap-6">
            {[
              { icon: AlertTriangle, title: "Trained once, forgotten", text: "Models are deployed and never re-evaluated against new applicant populations." },
              { icon: Eye, title: "Accuracy-only monitoring", text: "Teams track accuracy but ignore fairness, explainability, and stability over time." },
              { icon: Scale, title: "Hidden bias", text: "Disparate impact across gender, age, and region often goes completely undetected." },
              { icon: GitBranch, title: "No drift detection", text: "Shifts in applicant income, credit behavior, or macro conditions silently degrade models." },
              { icon: RefreshCcw, title: "Manual retraining", text: "Retraining decisions rely on gut feeling instead of data-driven triggers." },
              { icon: XCircle, title: "No governance gate", text: "There's no automated checkpoint before a risky model reaches production." },
            ].map((item, i) => (
              <motion.div key={i} initial="hidden" whileInView="show" viewport={{ once: true }} variants={fadeUp}>
                <Card>
                  <item.icon className="text-red-400 mb-4" size={28} />
                  <h3 className="font-semibold mb-2">{item.title}</h3>
                  <p className="text-muted text-sm">{item.text}</p>
                </Card>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Features / Solution */}
      <section id="features" className="px-6 py-24 bg-gradient-to-b from-transparent via-panel/40 to-transparent">
        <div className="max-w-6xl mx-auto">
          <SectionHeading
            kicker="The Solution"
            title="An automated governance layer for the full model lifecycle"
            subtitle="CreditSentinel sits between training and production, enforcing performance and fairness gates."
          />
          <div className="grid md:grid-cols-2 gap-6">
            {[
              { icon: Cpu, title: "Continuous Performance Monitoring", text: "Track accuracy, precision, recall, and F1 across every model version, in real time." },
              { icon: Scale, title: "Fairness Validation", text: "Audit approval-rate disparities, disparate impact, and equal opportunity gaps across gender, age, and region." },
              { icon: Activity, title: "Drift Detection", text: "Detect data and prediction drift using PSI-style statistical tests, with automated retraining triggers." },
              { icon: Lock, title: "Automated Governance", text: "Models reach production only if they pass both performance AND fairness gates — no exceptions." },
              { icon: Database, title: "Full Audit Trail", text: "Every training run, audit, and governance decision is logged for compliance and traceability." },
              { icon: CheckCircle2, title: "Explainable Predictions", text: "Every risk score ships with a feature-level explanation of what drove the decision." },
            ].map((item, i) => (
              <motion.div key={i} initial="hidden" whileInView="show" viewport={{ once: true }} variants={fadeUp}>
                <Card className="flex gap-4 items-start">
                  <div className="bg-accent/10 p-3 rounded-xl">
                    <item.icon className="text-accent" size={22} />
                  </div>
                  <div>
                    <h3 className="font-semibold mb-1">{item.title}</h3>
                    <p className="text-muted text-sm">{item.text}</p>
                  </div>
                </Card>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Workflow */}
      <section id="workflow" className="px-6 py-24">
        <div className="max-w-5xl mx-auto">
          <SectionHeading kicker="How it works" title="From raw data to governed deployment" />
          <div className="flex flex-col gap-3">
            {[
              "Data Ingestion", "Model Training", "Experiment Tracking", "Performance Evaluation",
              "Fairness Audit", "Governance Gate", "Model Deployment", "Continuous Monitoring", "Retraining Trigger",
            ].map((step, i) => (
              <motion.div key={i} initial="hidden" whileInView="show" viewport={{ once: true }} variants={fadeUp}
                className="glass flex items-center gap-4 px-6 py-4">
                <span className="w-8 h-8 rounded-full bg-accent/10 text-accent flex items-center justify-center text-sm font-bold border border-accent/30">
                  {i + 1}
                </span>
                <span className="font-medium">{step}</span>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="px-6 py-24">
        <Card className="max-w-4xl mx-auto text-center py-14 shadow-glow">
          <h2 className="text-3xl font-bold mb-4">Ready to govern your credit risk models?</h2>
          <p className="text-muted mb-8">Get a full demo workspace with synthetic lending data in seconds.</p>
          <Button onClick={() => navigate("/register")}>Create free workspace</Button>
        </Card>
      </section>

      <footer className="px-6 py-10 text-center text-muted text-sm border-t border-white/5">
        © {new Date().getFullYear()} CreditSentinel — A monitoring shield for smarter and fairer lending models.
      </footer>
    </div>
  );
}
