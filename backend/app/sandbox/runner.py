"""Sandbox execution coordinator orchestrating ephemeral container lifecycle and before/after verification."""

from datetime import datetime, timezone
import time
from typing import Optional, Tuple

from app.core.logging import logger
from app.sandbox.container_manager import (
    DockerSandboxContainer,
    container_manager,
    is_docker_available,
)
from app.sandbox.dependency_detector import dependency_manager
from app.sandbox.patch_applier import patch_applier
from app.sandbox.schemas import (
    BeforeAfterComparison,
    ExecutionStatus,
    ExecutionVerdict,
    SandboxExecution,
    SandboxExecutionRequest,
    TestRunResult,
)
from app.sandbox.test_runner import test_runner
from app.sandbox.workspace_prep import workspace_preparer


class SandboxExecutionRunner:
    """Executes end-to-end patch validation inside isolated Docker containers."""

    def compare_results(
        self,
        baseline: Optional[TestRunResult],
        patched: Optional[TestRunResult],
        patch_applied: bool,
    ) -> BeforeAfterComparison:
        """Computes comparative before-and-after metrics and determines the validation verdict."""
        if not patch_applied:
            return BeforeAfterComparison(
                verdict=ExecutionVerdict.PATCH_APPLICATION_FAILED,
                summary="Patch could not be applied cleanly to the codebase.",
            )

        if not patched:
            return BeforeAfterComparison(
                verdict=ExecutionVerdict.ENVIRONMENT_ERROR,
                summary="Patched test execution was not completed.",
            )

        # No tests discovered
        if patched.status == "no_tests_found" and (not baseline or baseline.status == "no_tests_found"):
            return BeforeAfterComparison(
                baseline_status=baseline.status if baseline else None,
                patched_status=patched.status,
                verdict=ExecutionVerdict.NO_TESTS,
                summary="Patch applied cleanly. No automated test suites were discovered in the repository.",
            )

        # Baseline was skipped
        if not baseline:
            if patched.is_success:
                return BeforeAfterComparison(
                    patched_status=patched.status,
                    patched_passed=patched.passed_count,
                    patched_failed=patched.failed_count,
                    verdict=ExecutionVerdict.SUCCESS,
                    summary=f"Patched tests executed successfully ({patched.passed_count} passed).",
                )
            return BeforeAfterComparison(
                patched_status=patched.status,
                patched_passed=patched.passed_count,
                patched_failed=patched.failed_count,
                verdict=ExecutionVerdict.TEST_FAILURE,
                summary=f"Patched tests failed ({patched.failed_count} failure(s)).",
            )

        b_pass = baseline.passed_count
        b_fail = baseline.failed_count + baseline.error_count
        p_pass = patched.passed_count
        p_fail = patched.failed_count + patched.error_count

        tests_fixed = max(0, b_fail - p_fail)
        tests_regressed = max(0, p_fail - b_fail)

        # 1. Success: Baseline failed, now patched passes
        if not baseline.is_success and patched.is_success:
            verdict = ExecutionVerdict.SUCCESS
            summary = (
                f"Patch verification SUCCESS: {b_fail} failing test(s) resolved. "
                f"All {p_pass} test(s) now pass cleanly."
            )
        # 2. Success: Both pass without regression
        elif baseline.is_success and patched.is_success:
            verdict = ExecutionVerdict.SUCCESS
            summary = (
                f"Patch verification SUCCESS: All {p_pass} test(s) pass cleanly. "
                "No regressions detected."
            )
        # 3. Regression: Baseline passed, but patched fails
        elif baseline.is_success and not patched.is_success:
            verdict = ExecutionVerdict.REGRESSION
            summary = (
                f"REGRESSION detected: Baseline passed, but {p_fail} test(s) failed "
                "after applying the proposed patch."
            )
        # 4. Test failure persists
        else:
            verdict = ExecutionVerdict.TEST_FAILURE
            summary = (
                f"Test failure persists: {p_fail} test(s) failed after patch "
                f"(baseline failures: {b_fail})."
            )

        return BeforeAfterComparison(
            baseline_status=baseline.status,
            patched_status=patched.status,
            baseline_passed=b_pass,
            baseline_failed=b_fail,
            patched_passed=p_pass,
            patched_failed=p_fail,
            tests_fixed=tests_fixed,
            tests_regressed=tests_regressed,
            verdict=verdict,
            summary=summary,
        )

    async def execute(
        self,
        execution: SandboxExecution,
        patch_diff: str,
        request: SandboxExecutionRequest,
    ) -> SandboxExecution:
        """Executes the containerized validation workflow under strict security boundaries."""
        t0 = time.time()
        log_stream = []

        def _log(msg: str) -> None:
            now_str = datetime.now(timezone.utc).strftime("%H:%M:%S")
            line = f"[{now_str}] {msg}"
            log_stream.append(line)
            logger.info("[SandboxRunner] %s", msg)

        _log(f"Starting sandbox execution for patch '{execution.patch_id}' on repository '{execution.repository_id}'")

        # 1. Docker availability check
        execution.status = ExecutionStatus.INITIALIZING
        if not is_docker_available():
            err_msg = (
                "Docker engine is not running or unreachable on this host. "
                "Sandbox execution requires Docker Desktop or an accessible Docker daemon. "
                "Untrusted repository code will not be executed on the host."
            )
            _log(f"ABORTED: {err_msg}")
            execution.status = ExecutionStatus.FAILED
            execution.error_message = err_msg
            execution.duration_seconds = time.time() - t0
            execution.completed_at = datetime.now(timezone.utc).isoformat()
            execution.logs = "\n".join(log_stream)
            execution.comparison = BeforeAfterComparison(
                verdict=ExecutionVerdict.ENVIRONMENT_ERROR,
                summary=err_msg,
            )
            return execution

        container: Optional[DockerSandboxContainer] = None
        try:
            # 2. Spawn ephemeral container
            _log(f"Spawning isolated container (language: {execution.language}, network_mode=none)...")
            container = await container_manager.spawn_container(
                language=execution.language,
                network_enabled=request.allow_network_for_deps,
                timeout_seconds=request.timeout_seconds,
            )
            execution.container_id = container.container_id
            _log(f"Container spawned with ID: {container.short_id}")

            # 3. Transfer repository snapshot
            execution.status = ExecutionStatus.PREPARING
            _log("Packaging repository snapshot into secure tar archive...")
            tar_bytes = workspace_preparer.create_repository_tar(execution.repository_id)
            _log(f"Injecting snapshot ({len(tar_bytes) / 1024.0:.1f} KB) into container /workspace...")
            container.put_tar_bytes("/workspace", tar_bytes)
            _log("Repository snapshot successfully prepared inside container.")

            # 4. Baseline test execution (before applying patch)
            if request.run_baseline:
                execution.status = ExecutionStatus.RUNNING_TESTS
                _log("Running baseline test suite on unmodified code...")
                base_result = await test_runner.execute_tests(
                    container=container,
                    workdir="/workspace",
                    language=execution.language,
                    custom_command=request.custom_test_command,
                    timeout_seconds=float(request.timeout_seconds or 45),
                )
                execution.baseline_result = base_result
                _log(
                    f"Baseline test run completed: status={base_result.status}, "
                    f"passed={base_result.passed_count}, failed={base_result.failed_count} "
                    f"in {base_result.duration_seconds:.2f}s"
                )
                if base_result.stdout.strip():
                    log_stream.append(f"--- BASELINE STDOUT ---\n{base_result.stdout.strip()}")
                if base_result.stderr.strip():
                    log_stream.append(f"--- BASELINE STDERR ---\n{base_result.stderr.strip()}")

            # 5. Dependency installation
            execution.status = ExecutionStatus.INSTALLING_DEPENDENCIES
            _log("Checking for dependency manifests...")
            dep_res = await dependency_manager.install_dependencies_if_needed(
                container=container,
                workdir="/workspace",
                allow_network=request.allow_network_for_deps,
            )
            execution.dependencies_installed = dep_res.success
            if dep_res.manager:
                _log(f"Dependency detection: manager={dep_res.manager}, success={dep_res.success}")
            if not dep_res.success:
                _log(f"Dependency installation error: {dep_res.error_message}")

            # 6. Patch application inside container
            execution.status = ExecutionStatus.APPLYING_PATCH
            _log("Applying proposed unified-diff patch inside container...")
            patch_res = await patch_applier.apply_patch(
                container=container,
                patch_diff=patch_diff,
                target_workdir="/workspace",
            )
            execution.patch_applied = patch_res.success
            execution.modified_files = patch_res.modified_files

            if not patch_res.success:
                _log(f"PATCH FAILED: {patch_res.error_message}")
                execution.status = ExecutionStatus.FAILED
                execution.error_message = f"Patch application failed: {patch_res.error_message}"
                execution.comparison = BeforeAfterComparison(
                    verdict=ExecutionVerdict.PATCH_APPLICATION_FAILED,
                    summary=f"Patch application rejected inside container: {patch_res.error_message}",
                )
                return execution

            _log(f"Patch applied successfully. Modified files: {patch_res.modified_files}")

            # 7. Patched test execution (after applying patch)
            execution.status = ExecutionStatus.RUNNING_TESTS
            _log("Running test suite against patched repository code...")
            patched_result = await test_runner.execute_tests(
                container=container,
                workdir="/workspace",
                language=execution.language,
                custom_command=request.custom_test_command,
                timeout_seconds=float(request.timeout_seconds or 45),
            )
            execution.patched_result = patched_result
            _log(
                f"Patched test run completed: status={patched_result.status}, "
                f"passed={patched_result.passed_count}, failed={patched_result.failed_count} "
                f"in {patched_result.duration_seconds:.2f}s"
            )
            if patched_result.stdout.strip():
                log_stream.append(f"--- PATCHED STDOUT ---\n{patched_result.stdout.strip()}")
            if patched_result.stderr.strip():
                log_stream.append(f"--- PATCHED STDERR ---\n{patched_result.stderr.strip()}")

            # 8. Comparison and final verdict
            comp = self.compare_results(
                baseline=execution.baseline_result,
                patched=execution.patched_result,
                patch_applied=execution.patch_applied,
            )
            execution.comparison = comp
            _log(f"Execution verdict: {comp.verdict} — {comp.summary}")

            if patched_result.status == "timed_out":
                execution.status = ExecutionStatus.TIMED_OUT
                execution.error_message = "Test execution timed out inside sandbox container."
            elif comp.verdict in (ExecutionVerdict.SUCCESS, ExecutionVerdict.NO_TESTS):
                execution.status = ExecutionStatus.COMPLETED
            else:
                execution.status = ExecutionStatus.COMPLETED  # Tests ran completely, verdict captures failure

            return execution

        except Exception as e:
            logger.exception("[SandboxRunner] Unexpected container execution error")
            execution.status = ExecutionStatus.FAILED
            execution.error_message = f"Sandbox execution crash: {str(e)}"
            _log(f"CRASH: {str(e)}")
            execution.comparison = BeforeAfterComparison(
                verdict=ExecutionVerdict.ENVIRONMENT_ERROR,
                summary=f"Container execution crashed: {str(e)}",
            )
            return execution

        finally:
            # 9. Guaranteed container cleanup
            if container:
                _log(f"Cleaning up ephemeral container {container.short_id}...")
                container.cleanup()
                _log("Container stopped and removed.")

            execution.duration_seconds = time.time() - t0
            execution.completed_at = datetime.now(timezone.utc).isoformat()
            execution.logs = "\n".join(log_stream)
            _log(f"Sandbox execution finished in {execution.duration_seconds:.2f}s (status={execution.status})")


sandbox_runner = SandboxExecutionRunner()

