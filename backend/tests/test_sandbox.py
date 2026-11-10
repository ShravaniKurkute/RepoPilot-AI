"""Comprehensive test suite for Phase 6: Docker Sandbox Execution Engine."""

import io
import os
from pathlib import Path
import tarfile
import tempfile
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.sandbox.schemas import (
    ExecutionStatus,
    ExecutionVerdict,
    TestRunResult,
    BeforeAfterComparison,
    SandboxExecution,
    SandboxExecutionRequest,
)
from app.sandbox.container_manager import (
    DockerContainerManager,
    DockerSandboxContainer,
    is_docker_available,
)
from app.sandbox.workspace_prep import (
    WorkspacePreparer,
    DEFAULT_SNAPSHOT_EXCLUSIONS,
)
from app.sandbox.patch_applier import (
    InContainerPatchApplier,
    IN_CONTAINER_PATCH_SCRIPT,
)
from app.sandbox.dependency_detector import (
    DependencyManager,
)
from app.sandbox.test_runner import (
    ContainerTestRunner,
)
from app.sandbox.runner import (
    SandboxExecutionRunner,
)
from app.sandbox.service import sandbox_service

client = TestClient(app)


# ============================================================================
# 1. Container Lifecycle & Security Tests
# ============================================================================

@pytest.mark.asyncio
async def test_container_manager_security_configuration():
    """Verify ephemeral container is created with strict security constraints."""
    mock_docker_client = MagicMock()
    mock_container = MagicMock()
    mock_container.id = "mock_container_abc123"
    mock_container.short_id = "mock_abc123"
    mock_container.exec_run.return_value = MagicMock(exit_code=0, output=(b"", b""))
    mock_docker_client.containers.run.return_value = mock_container

    manager = DockerContainerManager(client=mock_docker_client)
    sandbox = await manager.spawn_container(
        language="python",
        network_enabled=False,
    )

    assert sandbox.container_id == "mock_container_abc123"
    mock_docker_client.containers.run.assert_called_once()
    _, kwargs = mock_docker_client.containers.run.call_args

    # Check security parameters
    assert kwargs.get("privileged") is False
    assert kwargs.get("network_mode") == "none"
    assert kwargs.get("mem_limit") == "2048m"
    assert kwargs.get("pids_limit") == 100
    assert kwargs.get("cap_drop") == ["ALL"]
    assert "no-new-privileges:true" in kwargs.get("security_opt", [])
    assert kwargs.get("working_dir") == "/workspace"


def test_container_manager_cleanup():
    """Verify container is stopped and forcefully removed with volumes upon cleanup."""
    mock_docker_client = MagicMock()
    mock_container = MagicMock()
    mock_container.id = "mock_container_clean123"
    mock_container.short_id = "mock_clean123"

    sandbox = DockerSandboxContainer(client=mock_docker_client, container=mock_container)
    sandbox.cleanup()

    mock_container.stop.assert_called_once_with(timeout=1)
    mock_container.remove.assert_called_once_with(force=True, v=True)


@pytest.mark.asyncio
async def test_container_exec_command_success():
    """Verify execution of in-container commands returns exit code and output."""
    mock_docker_client = MagicMock()
    mock_container = MagicMock()
    mock_container.id = "mock_exec123"
    mock_container.short_id = "mock_exec"
    mock_container.exec_run.return_value = MagicMock(
        exit_code=0,
        output=(b"Hello from container\n", b""),
    )

    sandbox = DockerSandboxContainer(client=mock_docker_client, container=mock_container)
    res = await sandbox.exec_command(["echo", "Hello from container"])

    assert res.exit_code == 0
    assert "Hello from container" in res.stdout
    assert res.is_success is True


# ============================================================================
# 2. Workspace Preparation & Path Safety Tests
# ============================================================================

def test_workspace_snapshot_tar_packaging_and_exclusions():
    """Verify workspace snapshot packages safe files and excludes git, pycache, node_modules."""
    with tempfile.TemporaryDirectory() as temp_root:
        repo_id = "test_repo_1"
        repo_dir = os.path.join(temp_root, repo_id, "source")
        os.makedirs(repo_dir, exist_ok=True)

        # Create normal files
        os.makedirs(os.path.join(repo_dir, "src"), exist_ok=True)
        with open(os.path.join(repo_dir, "src", "main.py"), "w", encoding="utf-8") as f:
            f.write("print('RepoPilot')\n")

        with open(os.path.join(repo_dir, "requirements.txt"), "w", encoding="utf-8") as f:
            f.write("pytest>=7.0.0\n")

        # Create ignored folders
        git_dir = os.path.join(repo_dir, ".git")
        os.makedirs(git_dir, exist_ok=True)
        with open(os.path.join(git_dir, "config"), "w", encoding="utf-8") as f:
            f.write("[core]\n")

        pycache_dir = os.path.join(repo_dir, "src", "__pycache__")
        os.makedirs(pycache_dir, exist_ok=True)
        with open(os.path.join(pycache_dir, "main.cpython-311.pyc"), "w", encoding="utf-8") as f:
            f.write("bytecode")

        node_modules_dir = os.path.join(repo_dir, "node_modules")
        os.makedirs(node_modules_dir, exist_ok=True)
        with open(os.path.join(node_modules_dir, "pkg.js"), "w", encoding="utf-8") as f:
            f.write("module.exports = {}")

        # Generate snapshot
        from pathlib import Path
        preparer = WorkspacePreparer(storage_root=Path(temp_root))
        tar_bytes = preparer.create_repository_tar(repo_id)
        assert len(tar_bytes) > 0

        # Inspect tar contents
        with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r") as tar:
            names = tar.getnames()
            assert "src/main.py" in names
            assert "requirements.txt" in names
            # Excluded directories must not appear
            assert not any(".git" in name for name in names)
            assert not any("__pycache__" in name for name in names)
            assert not any("node_modules" in name for name in names)


def test_default_exclusions_set():
    """Verify standard build and security exclusions are present."""
    assert ".git" in DEFAULT_SNAPSHOT_EXCLUSIONS
    assert "__pycache__" in DEFAULT_SNAPSHOT_EXCLUSIONS
    assert "node_modules" in DEFAULT_SNAPSHOT_EXCLUSIONS
    assert ".venv" in DEFAULT_SNAPSHOT_EXCLUSIONS


# ============================================================================
# 3. In-Container Patch Application Tests
# ============================================================================

def test_in_container_patch_script_template():
    """Verify the self-contained in-container Python patch applier contains safety checks."""
    assert "def parse_and_apply" in IN_CONTAINER_PATCH_SCRIPT
    assert "Security error" in IN_CONTAINER_PATCH_SCRIPT
    assert "escapes workspace root" in IN_CONTAINER_PATCH_SCRIPT


@pytest.mark.asyncio
async def test_apply_patch_in_container_mocked():
    """Verify patch injection, script execution, and response parsing."""
    mock_docker_client = MagicMock()
    mock_container = MagicMock()
    mock_container.id = "mock_container_patch"
    mock_container.short_id = "mock_patch"

    # Mock container exec_run:
    # 1. python3 _apply_patch.py patch.diff -> exit_code 0, stdout=["calculator.py"]
    # 2. rm -f patch.diff _apply_patch.py -> exit_code 0
    mock_container.exec_run.side_effect = [
        MagicMock(exit_code=0, output=(b'["calculator.py"]', b"")),
        MagicMock(exit_code=0, output=(b"", b"")),
    ]

    sandbox = DockerSandboxContainer(client=mock_docker_client, container=mock_container)
    applier = InContainerPatchApplier()

    sample_patch = (
        "--- a/calculator.py\n"
        "+++ b/calculator.py\n"
        "@@ -1,3 +1,4 @@\n"
        " def divide(a, b):\n"
        "+    if b == 0: raise ValueError('zero')\n"
        "     return a / b\n"
    )

    res = await applier.apply_patch(sandbox, sample_patch)

    assert res.success is True
    assert res.modified_files == ["calculator.py"]
    mock_container.put_archive.assert_called_once()


# ============================================================================
# 4. Dependency Detector Tests
# ============================================================================

@pytest.mark.asyncio
async def test_dependency_manager_manifest_detection():
    """Verify dependency detector identifies package manifests."""
    mock_docker_client = MagicMock()
    mock_container = MagicMock()
    mock_container.id = "mock_dep"
    mock_container.short_id = "dep"
    mock_container.exec_run.return_value = MagicMock(
        exit_code=0,
        output=(b"requirements.txt\napp.py\n", b""),
    )

    sandbox = DockerSandboxContainer(client=mock_docker_client, container=mock_container)
    detector = DependencyManager()
    manifests = await detector.detect_manifests(sandbox)

    assert "requirements.txt" in manifests


@pytest.mark.asyncio
async def test_dependency_manager_offline_policy():
    """Verify dependency manager respects offline airgap policy."""
    mock_docker_client = MagicMock()
    mock_container = MagicMock()
    mock_container.id = "mock_dep"
    mock_container.short_id = "dep"
    mock_container.exec_run.return_value = MagicMock(
        exit_code=0,
        output=(b"requirements.txt\napp.py\n", b""),
    )

    sandbox = DockerSandboxContainer(client=mock_docker_client, container=mock_container)
    detector = DependencyManager()
    res = await detector.install_dependencies_if_needed(sandbox, allow_network=False)

    assert res.attempted is False
    assert res.success is True


# ============================================================================
# 5. Test Runner & Output Parsing Tests
# ============================================================================

def test_parse_pytest_output_passed():
    """Verify parsing of clean passing pytest output."""
    stdout = (
        "============================= test session starts =============================\n"
        "rootdir: /workspace\n"
        "collected 5 items\n\n"
        "tests/test_math.py .....                                                 [100%]\n\n"
        "============================== 5 passed in 0.12s ==============================\n"
    )
    runner = ContainerTestRunner()
    result = runner.parse_test_output("pytest", "pytest -v", 0, stdout, "", 0.12)
    assert result.exit_code == 0
    assert result.passed_count == 5
    assert result.failed_count == 0
    assert result.error_count == 0
    assert result.total_count == 5
    assert result.status == "passed"
    assert result.is_success is True


def test_parse_pytest_output_failed():
    """Verify parsing of failing pytest output with failure and error counts."""
    stdout = (
        "============================= test session starts =============================\n"
        "tests/test_math.py ..F.E                                                 [100%]\n"
        "=================================== FAILURES ===================================\n"
        "_________________________________ test_divide __________________________________\n"
        "ZeroDivisionError: division by zero\n"
        "=========================== short test summary info ===========================\n"
        "FAILED tests/test_math.py::test_divide - ZeroDivisionError\n"
        "ERROR tests/test_math.py::test_broken - RuntimeError\n"
        "==================== 1 failed, 3 passed, 1 error in 0.45s ====================\n"
    )
    runner = ContainerTestRunner()
    result = runner.parse_test_output("pytest", "pytest -v", 1, stdout, "", 0.45)
    assert result.exit_code == 1
    assert result.passed_count == 3
    assert result.failed_count == 1
    assert result.error_count == 1
    assert result.total_count == 5
    assert result.status == "failed"
    assert result.is_success is False


def test_parse_unittest_output():
    """Verify parsing of standard python unittest output."""
    stdout = "Ran 8 tests in 0.045s\n\nOK\n"
    runner = ContainerTestRunner()
    result = runner.parse_test_output("unittest", "python3 -m unittest", 0, stdout, "", 0.045)
    assert result.exit_code == 0
    assert result.passed_count == 8
    assert result.failed_count == 0
    assert result.status == "passed"


def test_parse_npm_test_output():
    """Verify parsing of npm/jest test suite output."""
    stdout = (
        "PASS src/app.test.js\n"
        "Tests:       6 passed, 6 total\n"
        "Snapshots:   0 total\n"
        "Time:        1.234 s\n"
    )
    runner = ContainerTestRunner()
    result = runner.parse_test_output("npm_test", "npm test", 0, stdout, "", 1.234)
    assert result.exit_code == 0
    assert result.passed_count == 6
    assert result.failed_count == 0
    assert result.status == "passed"


# ============================================================================
# 6. Before / After Comparison & Verdict Determination Tests
# ============================================================================

def test_compare_results_fix_verified():
    """Verify comparison logic detects fix when baseline fails and patched passes."""
    baseline = TestRunResult(
        framework="pytest",
        command="pytest",
        exit_code=1,
        passed_count=4,
        failed_count=1,
        total_count=5,
        status="failed",
        stdout="FAILED test_div",
    )
    patched = TestRunResult(
        framework="pytest",
        command="pytest",
        exit_code=0,
        passed_count=5,
        failed_count=0,
        total_count=5,
        status="passed",
        stdout="5 passed in 0.1s",
    )

    runner = SandboxExecutionRunner()
    comparison = runner.compare_results(baseline, patched, patch_applied=True)
    assert comparison.verdict == ExecutionVerdict.SUCCESS
    assert comparison.tests_fixed == 1
    assert comparison.tests_regressed == 0
    assert "SUCCESS" in comparison.summary


def test_compare_results_regression_detected():
    """Verify comparison logic detects regression when baseline passes and patched fails."""
    baseline = TestRunResult(
        framework="pytest",
        command="pytest",
        exit_code=0,
        passed_count=5,
        failed_count=0,
        total_count=5,
        status="passed",
    )
    patched = TestRunResult(
        framework="pytest",
        command="pytest",
        exit_code=1,
        passed_count=4,
        failed_count=1,
        total_count=5,
        status="failed",
        stdout="FAILED test_existing_feature",
    )

    runner = SandboxExecutionRunner()
    comparison = runner.compare_results(baseline, patched, patch_applied=True)
    assert comparison.verdict == ExecutionVerdict.REGRESSION
    assert comparison.tests_regressed == 1
    assert "REGRESSION" in comparison.summary


def test_compare_results_patch_application_failed():
    """Verify verdict when patch application fails."""
    runner = SandboxExecutionRunner()
    comparison = runner.compare_results(None, None, patch_applied=False)
    assert comparison.verdict == ExecutionVerdict.PATCH_APPLICATION_FAILED


def test_compare_results_no_tests():
    """Verify verdict when repository has no tests."""
    baseline = TestRunResult(
        framework="pytest", command="pytest", exit_code=5, status="no_tests_found"
    )
    patched = TestRunResult(
        framework="pytest", command="pytest", exit_code=5, status="no_tests_found"
    )
    runner = SandboxExecutionRunner()
    comparison = runner.compare_results(baseline, patched, patch_applied=True)
    assert comparison.verdict == ExecutionVerdict.NO_TESTS


# ============================================================================
# 7. End-to-End Sandbox Runner Orchestration (Mocked)
# ============================================================================

@pytest.mark.asyncio
async def test_sandbox_runner_mocked_success():
    """Verify SandboxExecutionRunner orchestrates the complete before/after verification cycle."""
    mock_client = MagicMock()
    mock_container = MagicMock()
    mock_container.id = "mock_container_e2e"
    mock_container.short_id = "e2e_cont"

    baseline_output = b"FAILED tests/test_div.py::test_zero\n1 failed, 2 passed in 0.1s\n"
    patch_output = b'["math.py"]'
    patched_output = b"3 passed in 0.1s\n"

    # Sequence of exec_run calls:
    # 1. mkdir /workspace
    # 2. cat package.json (framework detection) -> fails
    # 3. which pytest -> succeeds
    # 4. baseline pytest execution -> exit 1
    # 5. ls -1a /workspace (dependency detection)
    # 6. python3 _apply_patch.py patch.diff -> exit 0
    # 7. rm -f patch.diff _apply_patch.py
    # 8. cat package.json (framework detection)
    # 9. which pytest -> succeeds
    # 10. patched pytest execution -> exit 0
    mock_container.exec_run.side_effect = [
        MagicMock(exit_code=0, output=(b"", b"")),             # mkdir
        MagicMock(exit_code=1, output=(b"", b"")),             # package.json
        MagicMock(exit_code=0, output=(b"/usr/bin/pytest", b"")), # which pytest
        MagicMock(exit_code=1, output=(baseline_output, b"")), # baseline pytest
        MagicMock(exit_code=0, output=(b"main.py", b"")),      # ls
        MagicMock(exit_code=0, output=(patch_output, b"")),    # patch applier
        MagicMock(exit_code=0, output=(b"", b"")),             # rm patch
        MagicMock(exit_code=1, output=(b"", b"")),             # package.json
        MagicMock(exit_code=0, output=(b"/usr/bin/pytest", b"")), # which pytest
        MagicMock(exit_code=0, output=(patched_output, b"")),  # patched pytest
    ]
    mock_client.containers.run.return_value = mock_container

    with tempfile.TemporaryDirectory() as temp_root:
        repo_id = "e2e_repo"
        repo_dir = os.path.join(temp_root, repo_id, "source")
        os.makedirs(repo_dir, exist_ok=True)
        with open(os.path.join(repo_dir, "math.py"), "w") as f:
            f.write("# dummy")

        runner = SandboxExecutionRunner()

        execution = SandboxExecution(
            id="exec_e2e_123",
            repository_id=repo_id,
            patch_id="patch_e2e_123",
            status=ExecutionStatus.PENDING,
            language="python",
            created_at="2026-11-09T00:00:00Z",
        )

        with patch("app.sandbox.runner.is_docker_available", return_value=True), \
             patch("app.sandbox.runner.container_manager", DockerContainerManager(client=mock_client)), \
             patch("app.sandbox.runner.workspace_preparer", WorkspacePreparer(storage_root=Path(temp_root))):
            result = await runner.execute(
                execution=execution,
                patch_diff="--- a/math.py\n+++ b/math.py\n@@ -1,1 +1,2 @@\n+fix\n",
                request=SandboxExecutionRequest(),
            )

        assert result.status == ExecutionStatus.COMPLETED
        assert result.comparison is not None
        assert result.comparison.verdict == ExecutionVerdict.SUCCESS
        assert result.patch_applied is True
        assert result.modified_files == ["math.py"]


# ============================================================================
# 8. API Endpoint Tests
# ============================================================================

def test_execute_endpoint_environment_error_when_docker_unavailable():
    """Verify /execute endpoint returns safe ENVIRONMENT_ERROR when Docker daemon is down."""
    mock_patch = MagicMock()
    mock_patch.id = "patch_dummy"
    mock_patch.repository_id = "repo_dummy"
    mock_patch.patch_content = "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-old\n+new\n"

    with patch("app.sandbox.service.patch_service.get_patch", return_value=mock_patch), \
         patch("app.sandbox.runner.is_docker_available", return_value=False):
        response = client.post(
            "/api/v1/repositories/repo_dummy/patches/patch_dummy/execute",
            json={},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        execution = data["data"]
        assert execution["status"] == "FAILED"
        assert execution["comparison"]["verdict"] == "ENVIRONMENT_ERROR"
        assert "Docker engine is not running" in execution["error_message"]


def test_get_execution_not_found():
    """Verify /executions/{id} returns 404 for unknown execution ID."""
    response = client.get("/api/v1/executions/non_existent_execution_id")
    assert response.status_code == 404


def test_get_execution_and_report_flow():
    """Verify storing an execution allows retrieval of status, logs, and report."""
    execution = SandboxExecution(
        id="exec_test_seed_123",
        repository_id="repo_seed_123",
        patch_id="patch_seed_123",
        status=ExecutionStatus.COMPLETED,
        language="python",
        container_id="c_123456",
        patch_applied=True,
        modified_files=["app.py"],
        comparison=BeforeAfterComparison(
            verdict=ExecutionVerdict.SUCCESS,
            summary="All tests passed cleanly.",
            baseline_passed=5,
            patched_passed=5,
        ),
        logs="[SandboxRunner] Execution started\n[SandboxRunner] All tests passed\n",
        duration_seconds=3.45,
        created_at="2026-11-09T00:00:00Z",
    )
    sandbox_service._save_local_execution(execution)

    # 1. GET /executions/{id}
    res_status = client.get(f"/api/v1/executions/{execution.id}")
    assert res_status.status_code == 200
    assert res_status.json()["data"]["id"] == execution.id
    assert res_status.json()["data"]["comparison"]["verdict"] == "SUCCESS"

    # 2. GET /executions/{id}/logs (raw text format)
    res_logs_raw = client.get(f"/api/v1/executions/{execution.id}/logs")
    assert res_logs_raw.status_code == 200
    assert "All tests passed" in res_logs_raw.text

    # 2b. GET /executions/{id}/logs?format=json
    res_logs_json = client.get(f"/api/v1/executions/{execution.id}/logs?format=json")
    assert res_logs_json.status_code == 200
    assert "All tests passed" in res_logs_json.json()["data"]["logs"]

    # 3. GET /executions/{id}/report
    res_report = client.get(f"/api/v1/executions/{execution.id}/report")
    assert res_report.status_code == 200
    report_data = res_report.json()["data"]
    assert report_data["execution_id"] == execution.id
    assert report_data["verdict"] == "SUCCESS"
    assert "app.py" in report_data["modified_files"]

    # 4. GET /repositories/{id}/executions
    res_repo_list = client.get(f"/api/v1/repositories/{execution.repository_id}/executions")
    assert res_repo_list.status_code == 200
    assert res_repo_list.json()["data"]["total_executions"] >= 1


# ============================================================================
# 9. Real Docker Integration Test (Conditional)
# ============================================================================

@pytest.mark.skipif(
    not is_docker_available(),
    reason="Docker daemon is not running on host machine. Integration test skipped.",
)
@pytest.mark.asyncio
async def test_real_docker_sandbox_execution():
    """Execute a real container sandbox test if Docker Desktop daemon is running."""
    import docker

    client_docker = docker.from_env()
    manager = DockerContainerManager(client=client_docker)

    sandbox = await manager.spawn_container(language="python", network_enabled=False)
    try:
        res = await sandbox.exec_command(["python3", "-c", "print(1+1)"])
        assert res.exit_code == 0
        assert "2" in res.stdout
    finally:
        sandbox.cleanup()
