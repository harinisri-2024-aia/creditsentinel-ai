"""
SHAP-style explainability for a single prediction.

CreditSentinel doesn't depend on the `shap` package (it's heavy and not always
installable in constrained environments). Instead this module produces the
same *shape* of output a SHAP TreeExplainer would: a signed contribution per
feature, expressed in probability points, that sums (approximately) to the
gap between the model's average prediction and this specific prediction.

Method: marginal contribution via feature ablation.
For each feature we re-run the model with that single feature replaced by the
training-set mean (i.e. "removed") and measure how much the predicted
probability moves. That movement, signed, is the feature's contribution:
  - positive contribution  -> pushed risk score UP (toward decline)
  - negative contribution  -> pushed risk score DOWN (toward approve)

This is a simplified, model-agnostic approximation of SHAP values (closer to
a single-order Shapley approximation than full SHAP, but visually and
directionally equivalent for the purposes of this product) and works for any
sklearn-compatible classifier, not just tree models.
"""
from typing import List, Dict
import numpy as np
import pandas as pd


def explain_prediction(model, scaler, features: List[str], row: pd.DataFrame, baseline_means: Dict[str, float]):
    """
    Returns a list of {feature, contribution, direction, value} sorted by
    absolute contribution, descending. `contribution` is in probability
    points (can be negative). `direction` is "risk_up" or "risk_down".
    """
    row_scaled = scaler.transform(row[features])
    base_proba = float(model.predict_proba(row_scaled)[0][1])

    contributions = []
    for feature in features:
        ablated = row.copy()
        ablated[feature] = baseline_means.get(feature, row.iloc[0][feature])
        ablated_scaled = scaler.transform(ablated[features])
        ablated_proba = float(model.predict_proba(ablated_scaled)[0][1])

        # If replacing this feature with the "average" applicant moves the
        # score down, then this feature's actual value was pushing risk up
        # (and vice versa).
        contribution = base_proba - ablated_proba
        contributions.append({
            "feature": feature,
            "value": float(row.iloc[0][feature]),
            "contribution": round(float(contribution) * 100, 2),  # probability points
            "direction": "risk_up" if contribution > 0 else ("risk_down" if contribution < 0 else "neutral"),
        })

    contributions.sort(key=lambda c: abs(c["contribution"]), reverse=True)
    return {
        "base_risk_score": round(base_proba * 100, 2),
        "contributions": contributions,
    }


def compute_baseline_means(reference_df: pd.DataFrame, features: List[str]) -> Dict[str, float]:
    return {f: float(reference_df[f].mean()) for f in features}


def compute_expected_risk_score(model, scaler, features: List[str], baseline_means: Dict[str, float]) -> float:
    """
    The model's predicted risk score (0-100) for an "average" applicant —
    i.e. every feature set to its training-set mean. This is the SHAP
    waterfall chart's starting point ("expected value"), analogous to
    `explainer.expected_value` in the `shap` package.
    """
    baseline_row = pd.DataFrame([{f: baseline_means.get(f, 0.0) for f in features}])
    baseline_scaled = scaler.transform(baseline_row[features])
    proba = float(model.predict_proba(baseline_scaled)[0][1])
    return round(proba * 100, 2)


def build_shap_waterfall(contributions: List[dict], base_risk_score: float, expected_risk_score: float, top_n: int = 8) -> dict:
    """
    Converts the signed per-feature contributions already computed by
    explain_prediction() into the canonical SHAP "waterfall" structure used
    by chart libraries (and by shap.plots.waterfall): a starting "expected
    value" (the model's average predicted risk across the training baseline),
    a sequence of cumulative steps — one per feature, ordered by contribution
    magnitude — and a final value equal to this prediction's risk score.

    This is purely a presentation-layer reshaping of data CreditSentinel
    already computes; it adds a chart, it does not change how predictions,
    decisions, or the existing `shap_explanation` bar-chart contributions are
    calculated.

    Rescaling note: explain_prediction()'s contributions come from ablating
    ONE feature at a time, which (like single-order Shapley approximations
    generally) doesn't always sum exactly to (final - expected) — most
    noticeably for very confident predictions near 0% or 100%, where
    swapping out a single feature barely moves an already-saturated
    probability. A true SHAP TreeExplainer guarantees this "additivity"
    property by construction. To keep the waterfall chart visually honest
    (bars that actually add up to the final risk score, matching what a real
    `shap.plots.waterfall` looks like) the contributions are proportionally
    rescaled here so they sum exactly to (final - expected) — each feature's
    *direction* (risk_up/risk_down) and *relative* share of the total impact
    is preserved unchanged; only the overall scale is corrected. The
    unscaled, original contributions remain available unchanged in
    `shap_explanation` for the existing bar chart.

    Returns:
        {
          "expected_value": float,      # average/baseline risk score (0-100)
          "final_value": float,         # this prediction's risk score (0-100)
          "steps": [
             {
               "feature": str, "label": str, "value": float,
               "contribution": float,      # signed, rescaled, probability points
               "raw_contribution": float,  # original unscaled contribution (matches shap_explanation)
               "direction": "risk_up" | "risk_down" | "neutral",
               "start": float,             # cumulative running total before this step
               "end": float,               # cumulative running total after this step
             }, ...
          ],
        }
    """
    label_map = {
        "age": "Age",
        "annual_income": "Annual Income",
        "credit_score": "Credit Score",
        "loan_amount": "Loan Amount",
        "loan_term_months": "Loan Term (months)",
        "existing_debt": "Existing Debt",
        "employment_years": "Employment Years",
        "num_credit_lines": "Number of Credit Lines",
    }

    ordered = sorted(contributions, key=lambda c: abs(c["contribution"]), reverse=True)
    shown = ordered[:top_n]
    remainder = ordered[top_n:]

    target_total = float(base_risk_score) - float(expected_risk_score)
    raw_total = sum(c["contribution"] for c in ordered)
    # Scale factor that makes the (signed) contributions sum to exactly the
    # gap between the expected value and this prediction. Guards against a
    # near-zero raw_total (e.g. a prediction right at the baseline) by
    # falling back to no rescaling in that edge case.
    scale = (target_total / raw_total) if abs(raw_total) > 1e-9 else 1.0

    steps = []
    running = float(expected_risk_score)
    for c in shown:
        scaled_contribution = round(c["contribution"] * scale, 2)
        start = running
        end = running + scaled_contribution
        steps.append({
            "feature": c["feature"],
            "label": label_map.get(c["feature"], c["feature"]),
            "value": c["value"],
            "contribution": scaled_contribution,
            "raw_contribution": c["contribution"],
            "direction": c["direction"],
            "start": round(start, 2),
            "end": round(end, 2),
        })
        running = end

    # Fold any remaining lower-impact features into a single "Other factors"
    # step so the waterfall stays readable, exactly like shap's own
    # waterfall plot does for high-dimensional inputs. This step absorbs any
    # residual rounding so the final cumulative total lands exactly on
    # final_value.
    other_total = round(float(base_risk_score) - running, 2)
    if remainder or abs(other_total) > 0.005:
        start = running
        end = running + other_total
        steps.append({
            "feature": "_other",
            "label": f"Other factors ({len(remainder)})" if remainder else "Other factors",
            "value": None,
            "contribution": other_total,
            "raw_contribution": round(sum(c["contribution"] for c in remainder), 2) if remainder else 0.0,
            "direction": "risk_up" if other_total > 0 else ("risk_down" if other_total < 0 else "neutral"),
            "start": round(start, 2),
            "end": round(end, 2),
        })
        running = end

    return {
        "expected_value": round(float(expected_risk_score), 2),
        "final_value": round(float(base_risk_score), 2),
        "steps": steps,
    }


def counterfactual_suggestion(contributions: List[dict], decision: str) -> List[dict]:
    """
    For a declined applicant, suggest the top risk-increasing factors and a
    plain-language nudge of what moving them would likely do. This is a
    lightweight, directional counterfactual (not a guaranteed re-score) meant
    to satisfy adverse-action "principal reasons" style explanation.
    """
    if decision != "DECLINE":
        return []

    risk_up = [c for c in contributions if c["direction"] == "risk_up"]
    risk_up.sort(key=lambda c: c["contribution"], reverse=True)

    label_map = {
        "age": "applicant age",
        "annual_income": "annual income",
        "credit_score": "credit score",
        "loan_amount": "requested loan amount",
        "loan_term_months": "loan term",
        "existing_debt": "existing debt",
        "employment_years": "years of employment",
        "num_credit_lines": "number of open credit lines",
    }

    suggestions = []
    for c in risk_up[:3]:
        label = label_map.get(c["feature"], c["feature"])
        if c["feature"] in ("annual_income", "credit_score", "employment_years"):
            hint = f"A higher {label} would likely reduce this applicant's risk score."
        elif c["feature"] in ("existing_debt", "loan_amount", "num_credit_lines"):
            hint = f"A lower {label} would likely reduce this applicant's risk score."
        else:
            hint = f"{label.capitalize()} was a contributing factor in this decision."
        suggestions.append({
            "feature": c["feature"],
            "label": label,
            "impact_points": c["contribution"],
            "hint": hint,
        })
    return suggestions
