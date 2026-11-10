"""Comprehensive test suite for Phase 5: Agentic Planning & Patch Generation."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch
import pytest
from fastapi.testclient import TestClient

from app.analysis.schemas import AnalysisRun, CodeIssue
from app.analysis.service import bug_detection_service
from app.database.models import FixPlanModel, PatchProposalModel
from app.main import app
from app.patch.graph import execute_patch_workflow
from app.patch.llm_provider import MockPatchLLMProvider
from app.patch.nodes.enrichment import enrich_context_node
from app.patch.nodes.generation import generate_patch_node
from app.patch.nodes.impact import impact_analysis_node
from app.patch.nodes.planning import plan_fix_node
from app.patch.nodes.risk import risk_assessment_node
from app.patch.nodes.understanding import understand_issue_node
from app.patch.nodes.validation import validate_patch_node
from app.patch.service import patch_service
from app.patch.state import AgentWorkflowState
from app.patch.validator import PatchValidator
from app.repository.service import repository_service

client = TestClient(app)


# -----------------------------------------------------------------------------
# Fixtures & Helpers
# -----------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def isolate_services(tmp_path):
    """Isolates repository, analysis, and patch services using temporary paths."""
    orig_repo_root = repository_service.storage_root
    orig_analysis_root = bug_detection_service.storage_root
    orig_patch_root = patch_service.storage_root

    repository_service.storage_root = tmp_path
    bug_detection_service.storage_root = tmp_path
    patch_service.storage_root = tmp_path

    yield tmp_path

    repository_service.storage_root = orig_repo_root
    bug_detection_service.storage_root = orig_analysis_root
    patch_service.storage_root = orig_patch_root


def setup_test_repository(root_dir: Path, repo_id: str = "repo_test_123") -> Path:
    """Creates a realistic repository directory structure with sample source code and an issue."""
    repo_dir = root_dir / repo_id
    src_dir = repo_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    calc_file = src_dir / "calculator.py"
    calc_code = (
        "def compute_ratio(total, count):\n"
        "    ratio = total / 0\n"
        "    return ratio\n"
    )
    calc_file.write_text(calc_code, encoding="utf-8")

    test_file = src_dir / "test_calculator.py"
    test_code = (
        "from src.calculator import compute_ratio\n\n"
        "def test_compute_ratio():\n"
        "    assert compute_ratio(10, 2) == 5.0\n"
    )
    test_file.write_text(test_code, encoding="utf-8")

    # Seed an issue in bug_detection_service
    issue = CodeIssue(
        issue_id="issue_div_zero_1",
        repository_id=repo_id,
        analysis_run_id="run_test_1",
        file_path="src/calculator.py",
        language="python",
        issue_title="Division by zero in compute_ratio",
        issue_description="The denominator in the division operation is hardcoded to 0.",
        category="logic_bug",
        subcategory="division_by_zero",
        severity="High",
        confidence_score=0.95,
        start_line=2,
        end_line=2,
        affected_symbol="compute_ratio",
        evidence="ratio = total / 0",
        technical_explanation="Hardcoded denominator 0 produces ZeroDivisionError when called.",
        potential_impact="Service crashes when calling compute_ratio.",
        suggested_fix="Replace hardcoded 0 with count parameter and validate count != 0.",
        cwe_id="CWE-369",
        status="Open",
    )
    from datetime import datetime, timezone

    run = AnalysisRun(
        run_id="run_test_1",
        repository_id=repo_id,
        status="completed",
        total_issues=1,
        started_at=datetime.now(timezone.utc).isoformat(),
        completed_at=datetime.now(timezone.utc).isoformat(),
    )
    bug_detection_service._save_local_run(repo_id, run)
    bug_detection_service._save_local_issues(repo_id, [issue])

    return repo_dir


# -----------------------------------------------------------------------------
# 1. Deterministic Patch Validator Tests
# -----------------------------------------------------------------------------
def test_patch_validator_valid(tmp_path):
    """Asserts that a well-formed unified diff applies cleanly in memory and computes correct metrics."""
    setup_test_repository(tmp_path, "repo_test_123")
    validator = PatchValidator(tmp_path / "repo_test_123")

    valid_diff = (
        "--- a/src/calculator.py\n"
        "+++ b/src/calculator.py\n"
        "@@ -1,3 +1,5 @@\n"
        " def compute_ratio(total, count):\n"
        "+    if count == 0:\n"
        "+        return 0.0\n"
        "-    ratio = total / 0\n"
        "+    ratio = total / count\n"
        "     return ratio\n"
    )

    res = validator.validate_patch(valid_diff, expected_target_file="src/calculator.py")
    assert res.is_valid is True
    assert res.error_message is None
    assert res.lines_added == 3
    assert res.lines_removed == 1
    assert res.hunks_count == 1
    assert "src/calculator.py" in res.affected_files
    assert "if count == 0:" in res.modified_snippets["src/calculator.py"]
    assert "ratio = total / 0" not in res.modified_snippets["src/calculator.py"]


def test_patch_validator_path_traversal(tmp_path):
    """Asserts that directory traversal attempts are strictly rejected."""
    setup_test_repository(tmp_path, "repo_test_123")
    validator = PatchValidator(tmp_path / "repo_test_123")

    traversal_diff = (
        "--- a/../../etc/passwd\n"
        "+++ b/../../etc/passwd\n"
        "@@ -1,1 +1,1 @@\n"
        "-root:x:0:0\n"
        "+root:x:0:0:hacked\n"
    )
    res = validator.validate_patch(traversal_diff)
    assert res.is_valid is False
    assert "Invalid or unsafe target file path" in res.error_message or "Path traversal" in res.error_message


def test_patch_validator_absolute_paths(tmp_path):
    """Asserts that absolute file paths and Windows drive letters are rejected."""
    setup_test_repository(tmp_path, "repo_test_123")
    validator = PatchValidator(tmp_path / "repo_test_123")

    win_abs_diff = (
        "--- a/C:/Windows/System32/drivers/etc/hosts\n"
        "+++ b/C:/Windows/System32/drivers/etc/hosts\n"
        "@@ -1,1 +1,1 @@\n"
        "-127.0.0.1 localhost\n"
        "+127.0.0.1 evil.com\n"
    )
    res = validator.validate_patch(win_abs_diff)
    assert res.is_valid is False

    posix_abs_diff = (
        "--- a//etc/shadow\n"
        "+++ b//etc/shadow\n"
        "@@ -1,1 +1,1 @@\n"
        "-root:*\n"
        "+root:evil\n"
    )
    res2 = validator.validate_patch(posix_abs_diff)
    assert res2.is_valid is False


def test_patch_validator_protected_files(tmp_path):
    """Asserts that attempts to modify protected .env, .git, or .gitignore files are rejected."""
    setup_test_repository(tmp_path, "repo_test_123")
    env_file = tmp_path / "repo_test_123" / ".env"
    env_file.write_text("SECRET=123", encoding="utf-8")

    validator = PatchValidator(tmp_path / "repo_test_123")

    env_diff = (
        "--- a/.env\n"
        "+++ b/.env\n"
        "@@ -1,1 +1,1 @@\n"
        "-SECRET=123\n"
        "+SECRET=leaked\n"
    )
    res = validator.validate_patch(env_diff)
    assert res.is_valid is False
    assert "protected file" in res.error_message.lower()


def test_patch_validator_missing_target_file(tmp_path):
    """Asserts that a patch referencing a non-existent file fails validation."""
    setup_test_repository(tmp_path, "repo_test_123")
    validator = PatchValidator(tmp_path / "repo_test_123")

    missing_diff = (
        "--- a/src/nonexistent.py\n"
        "+++ b/src/nonexistent.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-foo\n"
        "+bar\n"
    )
    res = validator.validate_patch(missing_diff)
    assert res.is_valid is False
    assert "does not exist" in res.error_message


def test_patch_validator_syntax_error(tmp_path):
    """Asserts that corrupt or malformed diffs fail with syntax error."""
    setup_test_repository(tmp_path, "repo_test_123")
    validator = PatchValidator(tmp_path / "repo_test_123")

    malformed = "I am not a diff at all, just plain text."
    res = validator.validate_patch(malformed)
    assert res.is_valid is False


def test_patch_validator_binary_diff_rejected(tmp_path):
    """Asserts that binary patch representations are rejected."""
    setup_test_repository(tmp_path, "repo_test_123")
    validator = PatchValidator(tmp_path / "repo_test_123")

    binary_diff = (
        "diff --git a/logo.png b/logo.png\n"
        "GIT binary patch\n"
        "literal 1234\n"
        "zc$}q0Uv"
    )
    res = validator.validate_patch(binary_diff)
    assert res.is_valid is False
    assert "binary" in res.error_message.lower()


def test_patch_validator_unexpected_target_file(tmp_path):
    """Asserts that modifying a different file than the target issue file is rejected."""
    setup_test_repository(tmp_path, "repo_test_123")
    validator = PatchValidator(tmp_path / "repo_test_123")

    diff_for_other_file = (
        "--- a/src/test_calculator.py\n"
        "+++ b/src/test_calculator.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-def test_compute_ratio():\n"
        "+def test_compute_ratio_new():\n"
    )
    res = validator.validate_patch(diff_for_other_file, expected_target_file="src/calculator.py")
    assert res.is_valid is False
    assert "instead of the identified issue file" in res.error_message


# -----------------------------------------------------------------------------
# 2. Agent Modular Nodes & Workflow Tests
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_agent_nodes_execution(tmp_path):
    """Tests the sequence of modular LangGraph nodes individually."""
    setup_test_repository(tmp_path, "repo_test_123")
    issue_data = {
        "issue_id": "issue_div_zero_1",
        "file_path": "src/calculator.py",
        "symbol_name": "compute_ratio",
        "title": "Division by zero in compute_ratio",
        "evidence": "ratio = total / 0",
        "line_number": 2,
    }

    state: AgentWorkflowState = {
        "repository_id": "repo_test_123",
        "issue_id": "issue_div_zero_1",
        "issue_data": issue_data,
        "target_file_path": "src/calculator.py",
        "workflow_status": "understanding_issue",
        "regeneration_count": 0,
        "max_regenerations": 2,
    }

    with patch("app.patch.nodes.planning.get_patch_llm_provider", return_value=MockPatchLLMProvider()), \
         patch("app.patch.nodes.generation.get_patch_llm_provider", return_value=MockPatchLLMProvider()):

        # Node 1: Understanding
        res1 = await understand_issue_node(state)
        state.update(res1)
        assert state["workflow_status"] == "retrieving_context"
        assert state.get("source_snapshot_hash") is not None

        # Node 2: Enrichment
        res2 = await enrich_context_node(state)
        state.update(res2)
        assert state["workflow_status"] == "planning_fix"
        assert "callers" in state["retrieved_context"]
        assert "related_tests" in state["retrieved_context"]

        # Node 3: Planning
        res3 = await plan_fix_node(state)
        state.update(res3)
        assert state["workflow_status"] == "analyzing_impact"
        assert "implementation_steps" in state["fix_plan"]

        # Node 4: Impact Analysis
        res4 = await impact_analysis_node(state)
        state.update(res4)
        assert state["workflow_status"] == "generating_patch"
        assert "risk_level" in state["impact_report"]

        # Node 5: Patch Generation
        res5 = await generate_patch_node(state)
        state.update(res5)
        assert state["workflow_status"] == "validating_patch"
        assert "--- a/src/calculator.py" in state["generated_patches"]

        # Node 6: Validation
        res6 = await validate_patch_node(state)
        state.update(res6)
        assert state["workflow_status"] == "assessing_risk"
        assert state["validation_results"]["is_valid"] is True
        assert state["lines_added"] > 0

        # Node 7: Risk Assessment
        res7 = await risk_assessment_node(state)
        state.update(res7)
        assert state["workflow_status"] == "awaiting_review"
        assert 0.0 <= state["confidence_score"] <= 1.0


@pytest.mark.asyncio
async def test_workflow_outdated_issue_detection(tmp_path):
    """Asserts that if the evidence line does not exist in the source code, workflow stops early."""
    setup_test_repository(tmp_path, "repo_test_123")
    calc_file = tmp_path / "repo_test_123" / "src" / "calculator.py"
    # Change source code so evidence no longer matches
    calc_file.write_text("def compute_ratio(total, count):\n    return total / count if count else 0.0\n", encoding="utf-8")

    issue_data = {
        "issue_id": "issue_div_zero_1",
        "file_path": "src/calculator.py",
        "evidence": "ratio = total / 0",  # no longer in file!
    }

    state: AgentWorkflowState = {
        "repository_id": "repo_test_123",
        "issue_id": "issue_div_zero_1",
        "issue_data": issue_data,
        "target_file_path": "src/calculator.py",
        "workflow_status": "understanding_issue",
    }

    res = await understand_issue_node(state)
    assert res["workflow_status"] == "issue_outdated"
    assert "Source code has changed" in res["error_details"]


@pytest.mark.asyncio
async def test_langgraph_bounded_retry_on_invalid_diff(tmp_path):
    """Asserts that the workflow regenerates on invalid diff up to max_regenerations."""
    setup_test_repository(tmp_path, "repo_test_123")
    repo_id = "repo_test_123"
    issue_id = "issue_div_zero_1"

    # Define an LLM provider that yields an invalid diff on attempt 1, but valid on attempt 2
    class AlternatingMockLLM(MockPatchLLMProvider):
        call_count = 0

        async def generate_patch_diff(self, prompt_text: str) -> str:
            self.call_count += 1
            if self.call_count == 1:
                return "MALFORMED DIFF WITHOUT PROPER FORMAT"
            return await super().generate_patch_diff(prompt_text)

    mock_llm = AlternatingMockLLM()

    with patch("app.patch.nodes.planning.get_patch_llm_provider", return_value=mock_llm), \
         patch("app.patch.nodes.generation.get_patch_llm_provider", return_value=mock_llm):

        proposal = await patch_service.generate_patch_proposal(repo_id, issue_id)
        assert proposal.validation_status == "valid"
        assert proposal.regeneration_attempt >= 1


# -----------------------------------------------------------------------------
# 3. Patch Service Lifecycle & Local JSON Persistence
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_patch_service_lifecycle(tmp_path):
    """Verifies fix plan creation, patch proposal generation, review, and regeneration."""
    setup_test_repository(tmp_path, "repo_test_123")
    repo_id = "repo_test_123"
    issue_id = "issue_div_zero_1"

    with patch("app.patch.nodes.planning.get_patch_llm_provider", return_value=MockPatchLLMProvider()), \
         patch("app.patch.nodes.generation.get_patch_llm_provider", return_value=MockPatchLLMProvider()):

        # 1. Create fix plan
        plan = await patch_service.create_fix_plan(repo_id, issue_id)
        assert plan.id.startswith("plan_")
        assert plan.issue_id == issue_id
        assert plan.repository_id == repo_id
        assert len(plan.implementation_steps) > 0

        # Verify local file persistence
        plan_file = tmp_path / repo_id / "fix_plans" / f"{plan.id}.json"
        assert plan_file.exists()

        # Retrieve plan
        fetched_plan = await patch_service.get_fix_plan(repo_id, issue_id)
        assert fetched_plan is not None
        assert fetched_plan.id == plan.id

        # 2. Generate patch proposal
        proposal = await patch_service.generate_patch_proposal(repo_id, issue_id)
        assert proposal.id.startswith("patch_")
        assert proposal.fix_plan_id == plan.id
        assert proposal.validation_status == "valid"
        assert proposal.review_status == "pending_review"

        patch_file = tmp_path / repo_id / "patch_proposals" / f"{proposal.id}.json"
        assert patch_file.exists()

        # 3. List proposals
        proposals = await patch_service.list_patches(repo_id)
        assert len(proposals) >= 1
        assert proposals[0].id == proposal.id

        # 4. Review proposal: approve
        reviewed = await patch_service.review_patch(proposal.id, decision="approved", feedback="Looks solid.")
        assert reviewed.review_status == "approved"
        assert reviewed.workflow_status == "approved"

        # 5. Regenerate proposal
        regenerated = await patch_service.regenerate_patch(proposal.id, feedback="Add docstring.")
        assert regenerated.id != proposal.id
        assert regenerated.validation_status == "valid"


# -----------------------------------------------------------------------------
# 4. REST API Endpoint Integration Tests (9 Endpoints)
# -----------------------------------------------------------------------------
def test_api_fix_plan_endpoints(tmp_path):
    """Tests POST and GET /api/v1/repositories/{repo_id}/issues/{issue_id}/fix-plan."""
    setup_test_repository(tmp_path, "repo_test_123")

    with patch("app.patch.nodes.planning.get_patch_llm_provider", return_value=MockPatchLLMProvider()), \
         patch("app.patch.nodes.generation.get_patch_llm_provider", return_value=MockPatchLLMProvider()):

        # 1. POST fix-plan
        res_post = client.post("/api/v1/repositories/repo_test_123/issues/issue_div_zero_1/fix-plan")
        assert res_post.status_code == 200
        data_post = res_post.json()
        assert data_post["success"] is True
        assert data_post["data"]["issue_id"] == "issue_div_zero_1"
        assert len(data_post["data"]["implementation_steps"]) > 0

        # 2. GET fix-plan
        res_get = client.get("/api/v1/repositories/repo_test_123/issues/issue_div_zero_1/fix-plan")
        assert res_get.status_code == 200
        data_get = res_get.json()
        assert data_get["success"] is True
        assert data_get["data"]["id"] == data_post["data"]["id"]


def test_api_patch_generation_and_listing(tmp_path):
    """Tests POST generate-patch and GET patches for repository."""
    setup_test_repository(tmp_path, "repo_test_123")

    with patch("app.patch.nodes.planning.get_patch_llm_provider", return_value=MockPatchLLMProvider()), \
         patch("app.patch.nodes.generation.get_patch_llm_provider", return_value=MockPatchLLMProvider()):

        # 1. POST generate-patch
        res_gen = client.post(
            "/api/v1/repositories/repo_test_123/issues/issue_div_zero_1/generate-patch",
            json={"feedback": "Make sure to handle None gracefully."},
        )
        assert res_gen.status_code == 200
        data_gen = res_gen.json()
        assert data_gen["success"] is True
        patch_id = data_gen["data"]["id"]
        assert patch_id.startswith("patch_")
        assert data_gen["data"]["validation_status"] == "valid"

        # 2. GET patches for repository
        res_list = client.get("/api/v1/repositories/repo_test_123/patches")
        assert res_list.status_code == 200
        data_list = res_list.json()
        assert data_list["success"] is True
        assert data_list["data"]["total_patches"] >= 1
        assert any(p["id"] == patch_id for p in data_list["data"]["patches"])


def test_api_patch_details_and_raw_diff(tmp_path):
    """Tests GET /api/v1/patches/{patch_id} and GET /api/v1/patches/{patch_id}/diff."""
    setup_test_repository(tmp_path, "repo_test_123")

    with patch("app.patch.nodes.planning.get_patch_llm_provider", return_value=MockPatchLLMProvider()), \
         patch("app.patch.nodes.generation.get_patch_llm_provider", return_value=MockPatchLLMProvider()):

        res_gen = client.post("/api/v1/repositories/repo_test_123/issues/issue_div_zero_1/generate-patch")
        patch_id = res_gen.json()["data"]["id"]

        # 1. GET /api/v1/patches/{patch_id}
        res_detail = client.get(f"/api/v1/patches/{patch_id}")
        assert res_detail.status_code == 200
        data_detail = res_detail.json()
        assert data_detail["success"] is True
        assert data_detail["data"]["id"] == patch_id
        assert "src/calculator.py" in data_detail["data"]["affected_files"]

        # 2. GET /api/v1/patches/{patch_id}/diff (raw diff text)
        res_diff_raw = client.get(f"/api/v1/patches/{patch_id}/diff")
        assert res_diff_raw.status_code == 200
        assert "--- a/src/calculator.py" in res_diff_raw.text
        assert "+++ b/src/calculator.py" in res_diff_raw.text

        # 3. GET /api/v1/patches/{patch_id}/diff?format=json
        res_diff_json = client.get(f"/api/v1/patches/{patch_id}/diff?format=json")
        assert res_diff_json.status_code == 200
        data_json = res_diff_json.json()
        assert data_json["success"] is True
        assert "--- a/src/calculator.py" in data_json["data"]["diff"]


def test_api_patch_review_and_status(tmp_path):
    """Tests POST /api/v1/patches/{patch_id}/review and GET /api/v1/patches/{patch_id}/status."""
    setup_test_repository(tmp_path, "repo_test_123")

    with patch("app.patch.nodes.planning.get_patch_llm_provider", return_value=MockPatchLLMProvider()), \
         patch("app.patch.nodes.generation.get_patch_llm_provider", return_value=MockPatchLLMProvider()):

        res_gen = client.post("/api/v1/repositories/repo_test_123/issues/issue_div_zero_1/generate-patch")
        patch_id = res_gen.json()["data"]["id"]

        # 1. POST /api/v1/patches/{patch_id}/review -> approve
        res_review = client.post(
            f"/api/v1/patches/{patch_id}/review",
            json={"decision": "approved", "reviewer_feedback": "Approved for integration."},
        )
        assert res_review.status_code == 200
        data_rev = res_review.json()
        assert data_rev["success"] is True
        assert data_rev["data"]["review_status"] == "approved"

        # 2. GET /api/v1/patches/{patch_id}/status
        res_status = client.get(f"/api/v1/patches/{patch_id}/status")
        assert res_status.status_code == 200
        data_status = res_status.json()
        assert data_status["success"] is True
        assert data_status["data"]["status"] == "approved"
        assert data_status["data"]["review_status"] == "approved"


def test_api_patch_regeneration(tmp_path):
    """Tests POST /api/v1/patches/{patch_id}/regenerate."""
    setup_test_repository(tmp_path, "repo_test_123")

    with patch("app.patch.nodes.planning.get_patch_llm_provider", return_value=MockPatchLLMProvider()), \
         patch("app.patch.nodes.generation.get_patch_llm_provider", return_value=MockPatchLLMProvider()):

        res_gen = client.post("/api/v1/repositories/repo_test_123/issues/issue_div_zero_1/generate-patch")
        original_patch_id = res_gen.json()["data"]["id"]

        # Regenerate with reviewer feedback
        res_regen = client.post(
            f"/api/v1/patches/{original_patch_id}/regenerate",
            json={"feedback": "Add defensive assertions for extreme floats."},
        )
        assert res_regen.status_code == 200
        data_regen = res_regen.json()
        assert data_regen["success"] is True
        new_patch_id = data_regen["data"]["id"]
        assert new_patch_id.startswith("patch_")
        assert data_regen["data"]["validation_status"] == "valid"


def test_api_404_not_found_handling():
    """Asserts that 404 is properly returned for non-existent plans, patches, and invalid repositories."""
    res_plan = client.get("/api/v1/repositories/nonexistent_repo/issues/nonexistent_issue/fix-plan")
    assert res_plan.status_code == 404

    res_patch = client.get("/api/v1/patches/patch_nonexistent_999")
    assert res_patch.status_code == 404

    res_diff = client.get("/api/v1/patches/patch_nonexistent_999/diff")
    assert res_diff.status_code == 404

    res_review = client.post(
        "/api/v1/patches/patch_nonexistent_999/review",
        json={"decision": "rejected", "reviewer_feedback": "Not found test."},
    )
    assert res_review.status_code == 404


@pytest.mark.asyncio
async def test_enrich_context_with_populated_call_graph(tmp_path):
    """Regression test: verifies that enrich_context_node correctly processes a call_graph list without .edges AttributeError."""
    from app.code_analysis.schemas import (
        CallGraphEdge,
        FileAnalysisResult,
        RepositoryAnalysisResponse,
        RepositoryAnalysisSummary,
        Symbol,
        SourceLocation,
    )
    from app.code_analysis.service import code_analysis_service

    setup_test_repository(tmp_path, "repo_callgraph_test")
    repo_id = "repo_callgraph_test"

    # Mock call graph edges as a plain list (exact schema returned by Phase 2)
    edges = [
        CallGraphEdge(
            id="edge_1",
            caller_id="sym_main",
            caller_name="main_runner",
            caller_file="src/main.py",
            callee_name="compute_ratio",
            resolved_callee_id="sym_compute_ratio",
            resolved_callee_file="src/calculator.py",
            is_resolved=True,
            line_number=10,
        ),
        CallGraphEdge(
            id="edge_2",
            caller_id="sym_compute_ratio",
            caller_name="compute_ratio",
            caller_file="src/calculator.py",
            callee_name="helper_calc",
            resolved_callee_id=None,
            resolved_callee_file=None,
            is_resolved=False,
            line_number=2,
        ),
    ]

    sym = Symbol(
        id="sym_compute_ratio",
        name="compute_ratio",
        symbol_type="function",
        language="python",
        file_path="src/calculator.py",
        location=SourceLocation(start_line=1, start_column=1, end_line=3, end_column=16),
        is_exported=True,
    )

    file_result = FileAnalysisResult(
        file_path="src/calculator.py",
        language="python",
        status="success",
        symbols=[sym],
        dependencies=[],
        imports=[],
        metrics={"lines": 3},
    )

    summary = RepositoryAnalysisSummary(
        repository_id=repo_id,
        total_files=1,
        analyzed_files=1,
        total_symbols=1,
        total_dependencies=0,
        total_imports=0,
        total_call_edges=2,
        resolved_call_edges=1,
        analyzed_at="2026-11-07T00:00:00Z",
    )

    analysis_res = RepositoryAnalysisResponse(
        summary=summary,
        symbols=[sym],
        dependencies={},
        call_graph=edges,  # Plain List[CallGraphEdge]!
        files={"src/calculator.py": file_result},
    )

    with patch.object(code_analysis_service, "get_analysis", return_value=analysis_res):
        state: AgentWorkflowState = {
            "repository_id": repo_id,
            "issue_id": "issue_div_zero_1",
            "issue_data": {
                "file_path": "src/calculator.py",
                "affected_symbol": "compute_ratio",
            },
            "target_file_path": "src/calculator.py",
            "workflow_status": "retrieving_context",
        }

        # This previously raised AttributeError: 'list' object has no attribute 'edges'
        res = await enrich_context_node(state)
        assert res["workflow_status"] == "planning_fix"
        ctx = res["retrieved_context"]
        assert "main_runner" in ctx["callers"]
        assert "helper_calc" in ctx["callees"]


@pytest.mark.asyncio
async def test_process_three_issues_independently(tmp_path):
    """Verifies that ZeroDivisionError, SQL Injection, and Maximum Initialization bugs can be processed end-to-end independently."""
    from datetime import datetime, timezone

    repo_id = "repo_multi_bug_test"
    repo_dir = tmp_path / repo_id
    repo_dir.mkdir(parents=True, exist_ok=True)

    # Write buggy_code.py to repository
    buggy_code = (
        "def calculate_average(numbers):\n"
        "    total = sum(numbers)\n"
        "    average = total / len(numbers)\n"
        "    return average\n"
        "\n"
        "\n"
        "def get_user(user_id):\n"
        '    query = "SELECT * FROM users WHERE id = " + user_id\n'
        "    return query\n"
        "\n"
        "\n"
        "def find_maximum(numbers):\n"
        "    maximum = 0\n"
        "\n"
        "    for num in numbers:\n"
        "        if num > maximum:\n"
        "            maximum = num\n"
        "\n"
        "    return maximum\n"
    )
    code_file = repo_dir / "buggy_code.py"
    code_file.write_text(buggy_code, encoding="utf-8")

    # Define the 3 distinct issues
    issue_zero_div = CodeIssue(
        issue_id="issue_zero_div_avg",
        repository_id=repo_id,
        analysis_run_id="run_multi_1",
        file_path="buggy_code.py",
        language="python",
        issue_title="Division by zero in calculate_average",
        issue_description="Empty numbers list results in ZeroDivisionError when dividing by len(numbers).",
        category="logic_bug",
        subcategory="division_by_zero",
        severity="High",
        confidence_score=0.92,
        start_line=3,
        end_line=3,
        affected_symbol="calculate_average",
        evidence="average = total / len(numbers)",
        technical_explanation="Denominator len(numbers) is zero when numbers is empty.",
        potential_impact="Service crashes when calculate_average([]) is called.",
        suggested_fix="Check if numbers is empty and return 0.0 before division.",
        status="Open",
    )

    issue_sqli = CodeIssue(
        issue_id="issue_sqli_user",
        repository_id=repo_id,
        analysis_run_id="run_multi_1",
        file_path="buggy_code.py",
        language="python",
        issue_title="SQL Injection in get_user",
        issue_description="Direct string concatenation of user_id in SQL query allows SQL injection.",
        category="security_vulnerability",
        subcategory="sql_injection",
        severity="Critical",
        confidence_score=0.98,
        start_line=8,
        end_line=8,
        affected_symbol="get_user",
        evidence='query = "SELECT * FROM users WHERE id = " + user_id',
        technical_explanation="Untrusted user input concatenated directly into query string without sanitization.",
        potential_impact="Unauthorized data extraction or database modification.",
        suggested_fix="Use parameterized SQL query placeholders.",
        cwe_id="CWE-89",
        status="Open",
    )

    issue_max_init = CodeIssue(
        issue_id="issue_max_init_bug",
        repository_id=repo_id,
        analysis_run_id="run_multi_1",
        file_path="buggy_code.py",
        language="python",
        issue_title="Incorrect maximum initialization in find_maximum",
        issue_description="maximum initialized to 0 fails for lists of negative numbers.",
        category="logic_bug",
        subcategory="variable_initialization",
        severity="Medium",
        confidence_score=0.89,
        start_line=13,
        end_line=13,
        affected_symbol="find_maximum",
        evidence="maximum = 0",
        technical_explanation="Initial value 0 is greater than any negative number, returning 0 incorrectly.",
        potential_impact="Incorrect calculation results when processing negative values.",
        suggested_fix="Initialize maximum to numbers[0] or use None guard.",
        status="Open",
    )

    run = AnalysisRun(
        run_id="run_multi_1",
        repository_id=repo_id,
        status="completed",
        total_issues=3,
        started_at=datetime.now(timezone.utc).isoformat(),
        completed_at=datetime.now(timezone.utc).isoformat(),
    )
    bug_detection_service._save_local_run(repo_id, run)
    bug_detection_service._save_local_issues(repo_id, [issue_zero_div, issue_sqli, issue_max_init])

    # Test each issue through the full Phase 5 pipeline using mock provider
    test_cases = [
        (issue_zero_div, "ZeroDivisionError"),
        (issue_sqli, "SQL Injection"),
        (issue_max_init, "Maximum initialization"),
    ]

    with patch("app.patch.nodes.planning.get_patch_llm_provider", return_value=MockPatchLLMProvider()), \
         patch("app.patch.nodes.generation.get_patch_llm_provider", return_value=MockPatchLLMProvider()):

        for issue, bug_name in test_cases:
            # 1. Generate Fix Plan
            plan = await patch_service.create_fix_plan(repo_id, issue.issue_id)
            assert plan.id.startswith("plan_")
            assert plan.issue_id == issue.issue_id
            assert len(plan.implementation_steps) > 0
            assert len(plan.recommended_tests) > 0

            # 2. Generate Patch Proposal
            proposal = await patch_service.generate_patch_proposal(repo_id, issue.issue_id)
            assert proposal.id.startswith("patch_")
            assert proposal.validation_status == "valid", f"Validation failed for {bug_name}: {proposal.validation_details}"
            assert proposal.lines_added > 0
            assert proposal.confidence_score > 0.7
            assert proposal.review_status == "pending_review"

            # 3. Review Patch Proposal: Approve
            reviewed = await patch_service.review_patch(proposal.id, decision="approved", feedback=f"Verified fix for {bug_name}.")
            assert reviewed.review_status == "approved"
            assert reviewed.workflow_status == "approved"

    # 4. Strict Safety Guarantee Check: verify file on disk was NOT modified
    current_disk_content = code_file.read_text(encoding="utf-8")
    assert current_disk_content == buggy_code, "Safety violation: repository file was unexpectedly modified on disk!"

