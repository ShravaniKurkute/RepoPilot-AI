"""Impact Analysis Node: analyzes caller impact, interface preservation, and assigns risk level."""

from typing import Any, Dict, List
from app.patch.state import AgentWorkflowState


async def impact_analysis_node(state: AgentWorkflowState) -> Dict[str, Any]:
    """Evaluates the proposed fix against call graphs, callers, and interface stability."""
    ctx = state.get("retrieved_context") or {}
    plan = state.get("fix_plan") or {}
    issue = state.get("issue_data") or {}

    callers: List[str] = ctx.get("callers") or []
    affected_files: List[str] = plan.get("affected_files") or []
    issue_severity = issue.get("severity", "Medium")
    issue_category = issue.get("category", "")

    # Calculate Risk Factors
    risk_factors: List[str] = []
    breaking_change_potential = False

    # Check caller count
    if len(callers) > 5:
        risk_factors.append(f"High caller fan-out ({len(callers)} functions invoke this symbol)")
    elif callers:
        risk_factors.append(f"Invoked by {len(callers)} external callers")

    # Check file count
    if len(affected_files) > 3:
        risk_factors.append(f"Multi-file modification touching {len(affected_files)} files")

    # Check security criticality
    if issue_severity == "Critical" or issue_category == "security_vulnerability":
        risk_factors.append("Security-sensitive vulnerability fix requiring careful verification")

    # Interface change keywords check
    solution_text = (plan.get("proposed_solution") or "").lower()
    if any(k in solution_text for k in ("signature", "parameter", "remove parameter", "breaking", "rename")):
        breaking_change_potential = True
        risk_factors.append("Potential function signature or public interface alteration")

    # Determine Risk Level: Low, Medium, High, Critical
    if breaking_change_potential and (len(callers) > 3 or issue_severity == "Critical"):
        risk_level = "Critical"
    elif len(callers) > 4 or len(affected_files) > 2 or breaking_change_potential:
        risk_level = "High"
    elif len(callers) > 0 or issue_severity in ("High", "Critical"):
        risk_level = "Medium"
    else:
        risk_level = "Low"

    impact_report = {
        "callers": callers,
        "caller_count": len(callers),
        "affected_files_count": len(affected_files),
        "breaking_change_potential": breaking_change_potential,
        "risk_factors": risk_factors,
        "risk_level": risk_level,
        "has_related_tests": bool(ctx.get("related_tests")),
    }

    # Update plan with assessed risk level
    if plan:
        plan["risk_level"] = risk_level
        plan["impact_report"] = impact_report

    return {
        "impact_report": impact_report,
        "fix_plan": plan,
        "workflow_status": "generating_patch",
    }

