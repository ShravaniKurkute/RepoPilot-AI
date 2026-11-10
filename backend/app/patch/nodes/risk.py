"""Risk Assessment Node: evaluates patch size, criticality, and calculates confidence score."""

from typing import Any, Dict, List
from app.patch.state import AgentWorkflowState


async def risk_assessment_node(state: AgentWorkflowState) -> Dict[str, Any]:
    """Calculates comprehensive patch risk, confidence score, and reviewer requirements."""
    plan = state.get("fix_plan") or {}
    impact = state.get("impact_report") or {}
    val = state.get("validation_results") or {}
    lines_added = state.get("lines_added", 0)
    lines_removed = state.get("lines_removed", 0)
    affected_files = list((state.get("modified_snippets") or {}).keys())

    total_churn = lines_added + lines_removed
    impact_risk = impact.get("risk_level", "Low")

    risk_factors: List[str] = list(impact.get("risk_factors") or [])
    reviewer_attention: List[str] = []

    # Large code churn factor
    if total_churn > 40:
        risk_factors.append(f"Large code churn ({total_churn} lines modified)")
        reviewer_attention.append("Verify comprehensive test coverage for large change scope")
    elif total_churn > 15:
        risk_factors.append(f"Moderate code churn ({total_churn} lines modified)")

    if len(affected_files) > 1:
        risk_factors.append(f"Multi-file change affecting {len(affected_files)} files")
        reviewer_attention.append("Check integration between modified files")

    # Evaluate confidence score
    base_confidence = 0.85
    if not val.get("is_valid", False):
        base_confidence -= 0.5
    if impact.get("breaking_change_potential"):
        base_confidence -= 0.15
        reviewer_attention.append("Validate public API contracts and caller call-sites")
    if total_churn > 50:
        base_confidence -= 0.1
    if not impact.get("has_related_tests"):
        reviewer_attention.append("No related test files detected; manual testing recommended")

    final_confidence = round(max(0.2, min(0.98, base_confidence)), 2)

    # Determine final Risk Level
    if "Critical" in impact_risk or (impact_risk == "High" and total_churn > 30):
        final_risk = "Critical"
    elif impact_risk == "High" or total_churn > 25:
        final_risk = "High"
    elif impact_risk == "Medium" or total_churn > 10:
        final_risk = "Medium"
    else:
        final_risk = "Low"

    risk_assessment = {
        "risk_level": final_risk,
        "confidence_score": final_confidence,
        "total_lines_changed": total_churn,
        "lines_added": lines_added,
        "lines_removed": lines_removed,
        "risk_factors": risk_factors,
        "reviewer_attention": reviewer_attention,
    }

    return {
        "risk_assessment": risk_assessment,
        "confidence_score": final_confidence,
        "workflow_status": "awaiting_review",
    }

