"""LangGraph StateGraph definition and workflow execution engine for patch generation."""

from typing import Any, Dict
from langgraph.graph import END, START, StateGraph

from app.core.logging import logger
from app.patch.nodes import (
    enrich_context_node,
    generate_patch_node,
    impact_analysis_node,
    plan_fix_node,
    risk_assessment_node,
    understand_issue_node,
    validate_patch_node,
)
from app.patch.state import AgentWorkflowState


def route_after_understanding(state: AgentWorkflowState) -> str:
    """Routes after issue understanding check."""
    status = state.get("workflow_status")
    if status in ("issue_outdated", "failed"):
        logger.warning("Workflow stopped at understanding node: status=%s", status)
        return END
    return "enrich_context"


def route_after_planning(state: AgentWorkflowState) -> str:
    """Routes after fix planning."""
    if state.get("workflow_status") == "failed":
        logger.warning("Workflow stopped at planning node: planning failed.")
        return END
    return "analyze_impact"


def route_after_generation(state: AgentWorkflowState) -> str:
    """Routes after patch generation."""
    if state.get("workflow_status") == "failed":
        return END
    return "validate_patch"


def route_after_validation(state: AgentWorkflowState) -> str:
    """Evaluates deterministic validation results, retrying within bounded limits."""
    status = state.get("workflow_status")
    if status == "patch_invalid":
        regen_count = state.get("regeneration_count", 0)
        max_regens = state.get("max_regenerations", 2)
        if regen_count < max_regens:
            logger.info("Patch validation failed. Retrying patch synthesis (attempt %d/%d)...", regen_count + 1, max_regens)
            return "generate_patch"
        logger.warning("Patch validation retries exhausted (%d/%d). Failing proposal.", regen_count, max_regens)
        return END
    return "assess_risk"


def build_patch_workflow_graph() -> StateGraph:
    """Constructs and compiles the full LangGraph state machine for patch generation."""
    workflow = StateGraph(AgentWorkflowState)

    # Add workflow nodes
    workflow.add_node("understand_issue", understand_issue_node)
    workflow.add_node("enrich_context", enrich_context_node)
    workflow.add_node("plan_fix", plan_fix_node)
    workflow.add_node("analyze_impact", impact_analysis_node)
    workflow.add_node("generate_patch", generate_patch_node)
    workflow.add_node("validate_patch", validate_patch_node)
    workflow.add_node("assess_risk", risk_assessment_node)

    # Add edges and conditional transitions
    workflow.add_edge(START, "understand_issue")

    workflow.add_conditional_edges(
        "understand_issue",
        route_after_understanding,
        {"enrich_context": "enrich_context", END: END},
    )

    workflow.add_edge("enrich_context", "plan_fix")

    workflow.add_conditional_edges(
        "plan_fix",
        route_after_planning,
        {"analyze_impact": "analyze_impact", END: END},
    )

    workflow.add_edge("analyze_impact", "generate_patch")

    workflow.add_conditional_edges(
        "generate_patch",
        route_after_generation,
        {"validate_patch": "validate_patch", END: END},
    )

    workflow.add_conditional_edges(
        "validate_patch",
        route_after_validation,
        {
            "assess_risk": "assess_risk",
            "generate_patch": "generate_patch",
            END: END,
        },
    )

    workflow.add_edge("assess_risk", END)

    return workflow


# Compiled singleton graph
patch_workflow_app = build_patch_workflow_graph().compile()


async def execute_patch_workflow(initial_state: AgentWorkflowState) -> AgentWorkflowState:
    """Executes the compiled LangGraph workflow asynchronously."""
    final_state = await patch_workflow_app.ainvoke(initial_state)
    return final_state

