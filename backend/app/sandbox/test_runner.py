"""Automated test execution engine and test output parser for container sandboxes."""

import re
from typing import List, Optional, Tuple
from app.core.logging import logger
from app.sandbox.container_manager import DockerSandboxContainer
from app.sandbox.schemas import TestRunResult


class ContainerTestRunner:
    """Executes language-specific test suites inside sandbox containers and parses results."""

    async def detect_test_suite(
        self,
        container: DockerSandboxContainer,
        workdir: str = "/workspace",
        language: str = "python",
    ) -> Tuple[str, List[str]]:
        """Discovers the test framework and constructs the execution command."""
        lang = language.lower().strip()

        if lang in ("javascript", "typescript", "node", "js", "ts"):
            # Check package.json for test script
            check = await container.exec_command(["cat", "package.json"], workdir=workdir)
            if check.is_success and '"test"' in check.stdout:
                return "npm_test", ["npm", "test"]
            return "npm_test", ["npm", "test", "--", "--passWithNoTests"]

        # Default to Python test frameworks
        # Check if pytest is available
        pt_check = await container.exec_command(["which", "pytest"], workdir=workdir)
        if pt_check.is_success:
            return "pytest", ["pytest", "-v", "--tb=short"]

        # Check python3 -m pytest
        py_pt_check = await container.exec_command(["python3", "-m", "pytest", "--version"], workdir=workdir)
        if py_pt_check.is_success:
            return "pytest", ["python3", "-m", "pytest", "-v", "--tb=short"]

        # Fallback to standard library unittest
        return "unittest", ["python3", "-m", "unittest", "discover", "-v"]

    def parse_test_output(
        self,
        framework: str,
        command_str: str,
        exit_code: int,
        stdout: str,
        stderr: str,
        duration: float,
    ) -> TestRunResult:
        """Extracts passed, failed, error, and skipped metrics from test output."""
        passed = 0
        failed = 0
        errors = 0
        skipped = 0

        combined = f"{stdout}\n{stderr}"

        # 1. Pytest summary line parser
        # Example: "= 2 passed, 1 failed, 1 error in 0.12s ="
        pt_summary_match = re.search(r"=+ (.*?) in \d+(?:\.\d+)?s? =+", combined)
        if pt_summary_match:
            summary_str = pt_summary_match.group(1)
            p_m = re.search(r"(\d+)\s+passed", summary_str)
            if p_m:
                passed = int(p_m.group(1))
            f_m = re.search(r"(\d+)\s+failed", summary_str)
            if f_m:
                failed = int(f_m.group(1))
            e_m = re.search(r"(\d+)\s+error", summary_str)
            if e_m:
                errors = int(e_m.group(1))
            s_m = re.search(r"(\d+)\s+skipped", summary_str)
            if s_m:
                skipped = int(s_m.group(1))
        else:
            # 2. Python unittest summary line parser
            # Example: "Ran 5 tests in 0.012s ... FAILED (failures=2, errors=1)"
            ran_m = re.search(r"Ran (\d+) tests? in", combined)
            if ran_m:
                total_ran = int(ran_m.group(1))
                fail_m = re.search(r"failures=(\d+)", combined)
                err_m = re.search(r"errors=(\d+)", combined)
                failed = int(fail_m.group(1)) if fail_m else 0
                errors = int(err_m.group(1)) if err_m else 0
                passed = max(0, total_ran - failed - errors)
            else:
                # 3. Jest / npm test summary parser
                # Example: "Tests: 1 failed, 2 passed, 3 total"
                jest_m = re.search(r"Tests:\s+([^\n]+)", combined)
                if jest_m:
                    j_str = jest_m.group(1)
                    p_m = re.search(r"(\d+)\s+passed", j_str)
                    if p_m:
                        passed = int(p_m.group(1))
                    f_m = re.search(r"(\d+)\s+failed", j_str)
                    if f_m:
                        failed = int(f_m.group(1))

        total = passed + failed + errors + skipped

        # Status determination
        if exit_code == 124:
            status = "timed_out"
        elif exit_code == 0:
            status = "passed"
        elif exit_code == 5 or ("no tests were found" in combined.lower() or "collected 0 items" in combined):
            status = "no_tests_found"
        elif failed > 0:
            status = "failed"
        elif errors > 0:
            status = "errored"
        else:
            status = "failed" if exit_code != 0 else "passed"

        return TestRunResult(
            framework=framework,
            command=command_str,
            exit_code=exit_code,
            duration_seconds=duration,
            passed_count=passed,
            failed_count=failed,
            error_count=errors,
            skipped_count=skipped,
            total_count=total,
            status=status,
            stdout=stdout,
            stderr=stderr,
        )

    async def execute_tests(
        self,
        container: DockerSandboxContainer,
        workdir: str = "/workspace",
        language: str = "python",
        custom_command: Optional[str] = None,
        timeout_seconds: float = 45.0,
    ) -> TestRunResult:
        """Executes tests inside the container and returns structured results."""
        if custom_command:
            framework = "custom"
            cmd = custom_command.split()
        else:
            framework, cmd = await self.detect_test_suite(container, workdir, language)

        cmd_str = " ".join(cmd)
        logger.info("[TestRunner] Executing tests inside %s: '%s'...", container.short_id, cmd_str)

        # Set PYTHONPATH=. for python test runs
        env = {"PYTHONPATH": "."} if "python" in language.lower() or framework in ("pytest", "unittest") else {}
        exec_res = await container.exec_command(cmd, workdir=workdir, environment=env, timeout=timeout_seconds)

        return self.parse_test_output(
            framework=framework,
            command_str=cmd_str,
            exit_code=exec_res.exit_code,
            stdout=exec_res.stdout,
            stderr=exec_res.stderr,
            duration=exec_res.duration_seconds,
        )


test_runner = ContainerTestRunner()
