"""Patch Generation Node: prompts AI provider to generate a precise unified-diff patch."""

from typing import Any, Dict

from app.patch.llm_provider import get_patch_llm_provider
from app.patch.state import AgentWorkflowState


def format_patch_generation_prompt(state: AgentWorkflowState) -> str:
    """Formats prompt instructing the model to synthesize a unified diff."""
    target_file = state.get("target_file_path", "main.py")
    issue = state.get("issue_data") or {}
    plan = state.get("fix_plan") or {}
    source_code = state.get("source_code_snapshot") or ""
    feedback = state.get("human_feedback") or ""
    validation_err = (state.get("validation_results") or {}).get("error_message") or ""

    prompt = (
        f"TARGET FILE: {target_file}\n"
        f"ISSUE TITLE: {issue.get('issue_title', 'Bug')}\n"
        f"CATEGORY: {issue.get('category')} ({issue.get('subcategory')})\n"
        f"EVIDENCE: \n```\n{issue.get('evidence', '')}\n```\n\n"
        f"APPROVED FIX PLAN:\n"
        f"Proposed Solution: {plan.get('proposed_solution', '')}\n"
        f"Steps: {', '.join(plan.get('implementation_steps', []))}\n\n"
    )

    if feedback:
        prompt += f"USER CORRECTION FEEDBACK:\n{feedback}\n\n"

    if validation_err:
        prompt += f"PREVIOUS ATTEMPT VALIDATION ERROR:\n{validation_err}\nPlease correct this issue.\n\n"

    prompt += (
        f"ORIGINAL SOURCE CODE FOR '{target_file}':\n"
        "```\n"
        f"{source_code}\n"
        "```\n\n"
        "STRICT REQUIREMENTS:\n"
        "1. Output ONLY a valid standard unified diff starting with:\n"
        f"--- a/{target_file}\n"
        f"+++ b/{target_file}\n"
        "2. Do NOT change unrelated functions, variable names, or formatting.\n"
        "3. Preserve exact line content for context lines (prefixed with a space ' ').\n"
        "4. Prefix deleted lines with '-' and added lines with '+'.\n"
        "5. Output NO markdown fences, explanations, or notes outside the diff."
    )
    return prompt


async def generate_patch_node(state: AgentWorkflowState) -> Dict[str, Any]:
    """Generates a unified diff using the active LLM provider."""
    llm = get_patch_llm_provider()
    prompt = format_patch_generation_prompt(state)

    regen_count = state.get("regeneration_count", 0) + 1

    try:
        raw_diff = await llm.generate_patch_diff(prompt)
    except Exception as e:
        return {
            "workflow_status": "failed",
            "error_details": f"Patch synthesis failed: {e}",
            "regeneration_count": regen_count,
        }

    return {
        "generated_patches": raw_diff,
        "regeneration_count": regen_count,
        "workflow_status": "validating_patch",
    }

