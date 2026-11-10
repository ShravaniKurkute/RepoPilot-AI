"""Fix Planning Node: orchestrates structured remediation plan generation."""

from typing import Any, Dict

from app.patch.llm_provider import get_patch_llm_provider
from app.patch.state import AgentWorkflowState


def format_planning_prompt(state: AgentWorkflowState) -> str:
    """Formats prompt for the fix planning agent."""
    issue = state.get("issue_data") or {}
    ctx = state.get("retrieved_context") or {}

    prompt = (
        f"TARGET FILE: {state.get('target_file_path')}\n"
        f"ISSUE TITLE: {issue.get('issue_title', 'Unknown Defect')}\n"
        f"CATEGORY: {issue.get('category')} / {issue.get('subcategory')}\n"
        f"SEVERITY: {issue.get('severity')}\n"
        f"LINE RANGE: {issue.get('start_line')} - {issue.get('end_line')}\n"
        f"AFFECTED SYMBOL: {issue.get('affected_symbol', '<module>')}\n"
        f"EVIDENCE: \n```\n{issue.get('evidence', '')}\n```\n"
        f"TECHNICAL EXPLANATION:\n{issue.get('technical_explanation', '')}\n"
        f"POTENTIAL IMPACT:\n{issue.get('potential_impact', '')}\n"
        f"SUGGESTED FIX HINT:\n{issue.get('suggested_fix', '')}\n\n"
        f"RETRIEVED ARCHITECTURAL CONTEXT:\n"
        f"- Known Callers: {', '.join(ctx.get('callers', [])) or 'None'}\n"
        f"- Internal Callees: {', '.join(ctx.get('callees', [])) or 'None'}\n"
        f"- Declared Imports: {', '.join(ctx.get('imports', [])) or 'None'}\n"
        f"- Related Test Files: {', '.join(ctx.get('related_tests', [])) or 'None'}\n\n"
        "SOURCE CODE CONTEXT:\n"
        f"```\n{state.get('source_code_snapshot', '')[:2500]}\n```\n\n"
        "INSTRUCTIONS:\n"
        "Create a comprehensive remediation plan. Respond with a JSON object strictly following this structure:\n"
        "{\n"
        '  "summary": "Concise summary of the proposed fix",\n'
        '  "root_cause": "Detailed root cause analysis",\n'
        '  "proposed_solution": "Concrete technical solution strategy",\n'
        '  "implementation_steps": ["step 1", "step 2", "step 3"],\n'
        '  "affected_files": ["file1.py"],\n'
        '  "expected_behavior": "How the repository code should behave after the fix",\n'
        '  "recommended_tests": ["test case 1", "test case 2"]\n'
        "}\n"
    )
    return prompt


async def plan_fix_node(state: AgentWorkflowState) -> Dict[str, Any]:
    """Generates a structured implementation plan using the AI provider."""
    llm = get_patch_llm_provider()
    prompt = format_planning_prompt(state)

    try:
        plan_dict = await llm.generate_fix_plan(prompt)
    except Exception as e:
        return {
            "workflow_status": "failed",
            "error_details": f"AI Fix Planning failed: {e}",
        }

    if not plan_dict or not plan_dict.get("proposed_solution"):
        return {
            "workflow_status": "failed",
            "error_details": "Fix Planning produced an empty or invalid implementation plan.",
        }

    # Ensure affected_files has target file
    affected = plan_dict.get("affected_files") or []
    target_f = state.get("target_file_path")
    if target_f and target_f not in affected:
        affected.append(target_f)
    plan_dict["affected_files"] = affected

    return {
        "fix_plan": plan_dict,
        "workflow_status": "analyzing_impact",
    }

