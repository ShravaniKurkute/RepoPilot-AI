"""Pydantic schemas and data models for Phase 6 Docker Sandbox Execution."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ExecutionStatus(str, Enum):
    """Lifecycle states of sandbox execution."""

    PENDING = "PENDING"
    INITIALIZING = "INITIALIZING"
    PREPARING = "PREPARING"
    APPLYING_PATCH = "APPLYING_PATCH"
    INSTALLING_DEPENDENCIES = "INSTALLING_DEPENDENCIES"
    RUNNING_TESTS = "RUNNING_TESTS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMED_OUT = "TIMED_OUT"


class ExecutionVerdict(str, Enum):
    """Outcome verdict comparing baseline vs patched execution."""

    SUCCESS = "SUCCESS"  # Tests passed or bug was resolved without regressing existing tests
    REGRESSION = "REGRESSION"  # Patched code broke tests that previously passed
    TEST_FAILURE = "TEST_FAILURE"  # Tests failed both before and after (fix was insufficient)
    PATCH_APPLICATION_FAILED = "PATCH_APPLICATION_FAILED"  # Patch could not be applied cleanly
    DEPENDENCY_ERROR = "DEPENDENCY_ERROR"  # Failed to install required dependencies
    TIMEOUT = "TIMEOUT"  # Execution exceeded resource/time quota
    ENVIRONMENT_ERROR = "ENVIRONMENT_ERROR"  # Docker daemon unreachable or container crashed
    NO_TESTS = "NO_TESTS"  # No automated tests detected or executed


class TestRunResult(BaseModel):
    """Detailed result of executing an automated test suite inside the container."""

    __test__ = False  # Prevent pytest from collecting this model as a test suite

    framework: str = Field(..., description="Test framework identified (e.g. pytest, npm_test)")
    command: str = Field(..., description="Exact command executed inside container")
    exit_code: int = Field(..., description="Process exit code (0 = success)")
    duration_seconds: float = Field(default=0.0, description="Test execution duration in seconds")
    passed_count: int = Field(default=0, description="Number of passed tests")
    failed_count: int = Field(default=0, description="Number of failed tests")
    error_count: int = Field(default=0, description="Number of test errors / crashes")
    skipped_count: int = Field(default=0, description="Number of skipped tests")
    total_count: int = Field(default=0, description="Total tests discovered and run")
    status: str = Field(default="unknown", description="'passed', 'failed', 'errored', 'timed_out', 'no_tests_found'")
    stdout: str = Field(default="", description="Captured standard output")
    stderr: str = Field(default="", description="Captured standard error")

    @property
    def is_success(self) -> bool:
        return self.status == "passed" and self.exit_code == 0


class BeforeAfterComparison(BaseModel):
    """Comparative analysis of baseline vs patched repository test runs."""

    baseline_status: Optional[str] = Field(None, description="Status of baseline test run")
    patched_status: Optional[str] = Field(None, description="Status of patched test run")
    baseline_passed: int = Field(default=0, description="Baseline passed test count")
    baseline_failed: int = Field(default=0, description="Baseline failed test count")
    patched_passed: int = Field(default=0, description="Patched passed test count")
    patched_failed: int = Field(default=0, description="Patched failed test count")
    tests_fixed: int = Field(default=0, description="Count of tests that failed in baseline but pass now")
    tests_regressed: int = Field(default=0, description="Count of tests that passed in baseline but fail now")
    verdict: ExecutionVerdict = Field(default=ExecutionVerdict.TEST_FAILURE, description="Overall validation verdict")
    summary: str = Field(default="", description="Human-readable explanation of comparison")


class SandboxExecutionRequest(BaseModel):
    """Request payload to initiate containerized patch execution."""

    timeout_seconds: Optional[int] = Field(default=60, ge=10, le=300, description="Execution timeout in seconds")
    run_baseline: bool = Field(default=True, description="Whether to run baseline tests before applying patch")
    allow_network_for_deps: bool = Field(default=False, description="Whether to allow network access during dependency install")
    custom_test_command: Optional[str] = Field(default=None, description="Optional custom test command override")


class SandboxExecution(BaseModel):
    """Full execution record for a patch validation run in an isolated container."""

    id: str = Field(..., description="Unique execution identifier (e.g. exec_123456)")
    repository_id: str = Field(..., description="Target repository ID")
    patch_id: str = Field(..., description="Target patch proposal ID")
    status: ExecutionStatus = Field(default=ExecutionStatus.PENDING, description="Current execution lifecycle state")
    language: str = Field(default="python", description="Primary repository language")
    container_id: Optional[str] = Field(None, description="Docker container ID if spawned")
    patch_applied: bool = Field(default=False, description="Whether patch applied cleanly inside container")
    modified_files: List[str] = Field(default_factory=list, description="Files modified by the patch")
    dependencies_installed: bool = Field(default=False, description="Whether dependencies were installed")
    baseline_result: Optional[TestRunResult] = Field(None, description="Baseline test execution results")
    patched_result: Optional[TestRunResult] = Field(None, description="Patched test execution results")
    comparison: Optional[BeforeAfterComparison] = Field(None, description="Before and after comparison analysis")
    duration_seconds: float = Field(default=0.0, description="Total execution duration in seconds")
    logs: str = Field(default="", description="Combined container execution logs")
    error_message: Optional[str] = Field(None, description="Error message if execution failed")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    completed_at: Optional[str] = Field(None, description="ISO 8601 completion timestamp")


class ExecutionListResponse(BaseModel):
    """List response for repository sandbox executions."""

    repository_id: str
    total_executions: int
    executions: List[SandboxExecution]


class ExecutionReportResponse(BaseModel):
    """Summary report for an execution run."""

    execution_id: str
    repository_id: str
    patch_id: str
    status: ExecutionStatus
    verdict: ExecutionVerdict
    comparison: BeforeAfterComparison
    modified_files: List[str]
    duration_seconds: float
    error_message: Optional[str] = None
    created_at: str
    completed_at: Optional[str] = None
