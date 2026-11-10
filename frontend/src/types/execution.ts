/**
 * TypeScript definitions for Phase 6: Docker Sandbox Execution and Automated Patch Validation.
 */

export type ExecutionStatus =
  | 'PENDING'
  | 'INITIALIZING'
  | 'PREPARING'
  | 'APPLYING_PATCH'
  | 'INSTALLING_DEPENDENCIES'
  | 'RUNNING_TESTS'
  | 'COMPLETED'
  | 'FAILED'
  | 'TIMED_OUT'
  | 'pending'
  | 'initializing'
  | 'preparing'
  | 'applying_patch'
  | 'installing_dependencies'
  | 'running_tests'
  | 'completed'
  | 'failed'
  | 'timed_out'

export type ExecutionVerdict =
  | 'SUCCESS'
  | 'REGRESSION'
  | 'TEST_FAILURE'
  | 'PATCH_APPLICATION_FAILED'
  | 'DEPENDENCY_ERROR'
  | 'TIMEOUT'
  | 'ENVIRONMENT_ERROR'
  | 'NO_TESTS'
  | 'success'
  | 'regression'
  | 'test_failure'
  | 'patch_application_failed'
  | 'dependency_error'
  | 'timeout'
  | 'environment_error'
  | 'no_tests'

export interface TestRunResult {
  framework: string
  command: string
  exit_code: number
  duration_seconds: number
  passed_count: number
  failed_count: number
  error_count: number
  skipped_count: number
  total_count: number
  status: string
  stdout: string
  stderr: string
}

export interface BeforeAfterComparison {
  baseline_status?: string | null
  patched_status?: string | null
  baseline_passed: number
  baseline_failed: number
  patched_passed: number
  patched_failed: number
  tests_fixed: number
  tests_regressed: number
  verdict: ExecutionVerdict
  summary: string
}

export interface SandboxExecutionRequest {
  timeout_seconds?: number
  run_baseline?: boolean
  allow_network_for_deps?: boolean
  custom_test_command?: string | null
}

export interface SandboxExecution {
  id: string
  repository_id: string
  patch_id: string
  status: ExecutionStatus
  language: string
  container_id?: string | null
  patch_applied: boolean
  modified_files: string[]
  dependencies_installed: boolean
  baseline_result?: TestRunResult | null
  patched_result?: TestRunResult | null
  comparison?: BeforeAfterComparison | null
  duration_seconds: number
  logs: string
  error_message?: string | null
  created_at: string
  completed_at?: string | null
}

export interface ExecutionListResponse {
  repository_id: string
  total_executions: number
  executions: SandboxExecution[]
}

export interface ExecutionReportResponse {
  execution_id: string
  repository_id: string
  patch_id: string
  status: ExecutionStatus
  verdict: ExecutionVerdict
  comparison: BeforeAfterComparison
  modified_files: string[]
  duration_seconds: number
  error_message?: string | null
  created_at: string
  completed_at?: string | null
}
