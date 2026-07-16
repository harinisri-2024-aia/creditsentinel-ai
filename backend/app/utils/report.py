"""
Compliance report generation (Feature 9).

Produces two export formats for a single model version:
  - CSV: flat key/value + tabular sections, easy to pull into a spreadsheet.
  - PDF: formatted report suitable for handing to a regulator or auditor.

Both formats cover the same content:
  - Model information (name, version, algorithm, created date)
  - Performance metrics (accuracy/precision/recall/F1)
  - Fairness results (per attribute, with thresholds used)
  - Drift results (latest + history summary)
  - Governance decision (approved/rejected + reason)
  - Audit history (chronological log entries for this model)
"""
import io
import csv
import datetime


def _fmt_pct(x):
    try:
        return f"{float(x) * 100:.1f}%"
    except (TypeError, ValueError):
        return str(x)


def build_report_context(model_version, fairness_audits, drift_reports, governance_logs, thresholds):
    """Assembles a plain-dict context shared by both the CSV and PDF builders."""
    return {
        "model": {
            "name": model_version.name,
            "version": model_version.version,
            "algorithm": model_version.algorithm,
            "status": model_version.status,
            "governance_decision": model_version.governance_decision,
            "fairness_status": model_version.fairness_status,
            "created_at": model_version.created_at.isoformat() if model_version.created_at else "",
        },
        "metrics": {
            "accuracy": model_version.accuracy,
            "precision": model_version.precision_score,
            "recall": model_version.recall_score,
            "f1": model_version.f1,
        },
        "fairness": [
            {
                "attribute": a.attribute,
                "disparate_impact": a.disparate_impact,
                "equal_opportunity_diff": a.equal_opportunity_diff,
                "passed": a.passed,
                "created_at": a.created_at.isoformat() if a.created_at else "",
            }
            for a in fairness_audits
        ],
        "thresholds": thresholds,
        "drift": [
            {
                "data_drift_score": d.data_drift_score,
                "prediction_drift_score": d.prediction_drift_score,
                "drift_detected": d.drift_detected,
                "retrain_recommended": d.retrain_recommended,
                "created_at": d.created_at.isoformat() if d.created_at else "",
            }
            for d in drift_reports
        ],
        "audit_history": [
            {
                "action": log.action,
                "details": log.details,
                "created_at": log.created_at.isoformat() if log.created_at else "",
            }
            for log in governance_logs
        ],
        "generated_at": datetime.datetime.utcnow().isoformat(),
    }


def build_csv_report(context: dict) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)

    writer.writerow(["CreditSentinel Compliance Report"])
    writer.writerow(["Generated At", context["generated_at"]])
    writer.writerow([])

    writer.writerow(["Model Information"])
    for k, v in context["model"].items():
        writer.writerow([k, v])
    writer.writerow([])

    writer.writerow(["Performance Metrics"])
    for k, v in context["metrics"].items():
        writer.writerow([k, v])
    writer.writerow([])

    writer.writerow(["Fairness Thresholds Used"])
    for k, v in context["thresholds"].items():
        writer.writerow([k, v])
    writer.writerow([])

    writer.writerow(["Fairness Results"])
    writer.writerow(["Attribute", "Disparate Impact", "Equal Opportunity Diff", "Passed", "Date"])
    for f in context["fairness"]:
        writer.writerow([f["attribute"], f["disparate_impact"], f["equal_opportunity_diff"], f["passed"], f["created_at"]])
    writer.writerow([])

    writer.writerow(["Drift Reports"])
    writer.writerow(["Data Drift Score", "Prediction Drift Score", "Drift Detected", "Retrain Recommended", "Date"])
    for d in context["drift"]:
        writer.writerow([d["data_drift_score"], d["prediction_drift_score"], d["drift_detected"], d["retrain_recommended"], d["created_at"]])
    writer.writerow([])

    writer.writerow(["Audit History"])
    writer.writerow(["Action", "Details", "Date"])
    for log in context["audit_history"]:
        writer.writerow([log["action"], log["details"], log["created_at"]])

    return buf.getvalue().encode("utf-8")


def build_pdf_report(context: dict) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.units import inch

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    styles = getSampleStyleSheet()
    accent = colors.HexColor("#0fae66")

    title_style = ParagraphStyle("TitleGreen", parent=styles["Title"], textColor=accent)
    heading_style = ParagraphStyle("Heading", parent=styles["Heading2"], textColor=accent, spaceBefore=14)

    elements = [
        Paragraph("CreditSentinel — Model Governance Compliance Report", title_style),
        Paragraph(f"Generated: {context['generated_at']} UTC", styles["Normal"]),
        Spacer(1, 0.2 * inch),
    ]

    def section_table(heading, rows, col_widths=None):
        elements.append(Paragraph(heading, heading_style))
        t = Table(rows, colWidths=col_widths)
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0e1410")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
        ]))
        elements.append(t)

    m = context["model"]
    section_table("Model Information", [
        ["Field", "Value"],
        ["Name", m["name"]], ["Version", m["version"]], ["Algorithm", m["algorithm"]],
        ["Status", m["status"]], ["Governance Decision", m["governance_decision"]],
        ["Fairness Status", m["fairness_status"]], ["Created At", m["created_at"]],
    ], col_widths=[2 * inch, 4 * inch])

    mt = context["metrics"]
    section_table("Performance Metrics", [
        ["Metric", "Value"],
        ["Accuracy", _fmt_pct(mt["accuracy"])],
        ["Precision", _fmt_pct(mt["precision"])],
        ["Recall", _fmt_pct(mt["recall"])],
        ["F1 Score", _fmt_pct(mt["f1"])],
    ], col_widths=[2 * inch, 4 * inch])

    th = context["thresholds"]
    fairness_rows = [["Attribute", "Disparate Impact", "Equal Opp. Diff", "Passed", "Date"]]
    for f in context["fairness"]:
        fairness_rows.append([f["attribute"], f["disparate_impact"], f["equal_opportunity_diff"],
                               "Yes" if f["passed"] else "No", f["created_at"][:19]])
    if len(fairness_rows) == 1:
        fairness_rows.append(["—", "—", "—", "—", "No audits run yet"])
    section_table(
        f"Fairness Results (thresholds: DI ≥ {th['disparate_impact_min']}, EOD ≤ {th['equal_opportunity_max']})",
        fairness_rows,
    )

    drift_rows = [["Data Drift", "Prediction Drift", "Detected", "Retrain Rec.", "Date"]]
    for d in context["drift"][:10]:
        drift_rows.append([d["data_drift_score"], d["prediction_drift_score"],
                            "Yes" if d["drift_detected"] else "No",
                            "Yes" if d["retrain_recommended"] else "No", d["created_at"][:19]])
    if len(drift_rows) == 1:
        drift_rows.append(["—", "—", "—", "—", "No drift checks run yet"])
    section_table("Drift Monitoring History (most recent 10)", drift_rows)

    audit_rows = [["Action", "Details", "Date"]]
    for log in context["audit_history"][:25]:
        audit_rows.append([log["action"], Paragraph(log["details"][:180], styles["Normal"]), log["created_at"][:19]])
    if len(audit_rows) == 1:
        audit_rows.append(["—", "No audit history", "—"])
    section_table("Audit History (most recent 25)", audit_rows, col_widths=[1.3 * inch, 3.7 * inch, 1.3 * inch])

    doc.build(elements)
    return buf.getvalue()
