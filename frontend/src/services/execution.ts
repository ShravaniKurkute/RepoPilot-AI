/**
 * Service client for Phase 6: Docker Sandbox Execution Engine.
 */

import type {
  ApiResponse,
  ExecutionListResponse,
  ExecutionReportResponse,
  SandboxExecution,
  SandboxExecutionRequest,
} from '../types'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1'

/**
 * Executes a fetch request with timeout protection via AbortController and logging.
 */
async function fetchWithTimeout<T>(
  url: string,
  options: RequestInit = {},
  timeoutMs: number = 180000,
  operationLabel: string = 'Docker Execution API'
): Promise<ApiResponse<T>> {
  const startTime = performance.now()
  console.log(`[Frontend ExecutionService] [${operationLabel}] ${options.method || 'GET'} ${url}`)

  const controller = new AbortController()
  const timeoutId = setTimeout(() => {
    controller.abort()
  }, timeoutMs)

  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    })

    const elapsed = ((performance.now() - startTime) / 1000).toFixed(2)
    console.log(`[Frontend ExecutionService] [${operationLabel}] Status ${response.status} in ${elapsed}s`)

    let payload: any
    try {
      payload = await response.json()
    } catch {
      payload = { detail: `Server responded with status ${response.status}` }
    }

    if (!response.ok) {
      const errorMsg = payload.detail || payload.message || `${operationLabel} failed (${response.status})`
      console.error(`[Frontend ExecutionService] [${operationLabel}] HTTP ${response.status} Error:`, errorMsg)
      throw new Error(errorMsg)
    }

    return payload
  } catch (err: unknown) {
    const elapsed = ((performance.now() - startTime) / 1000).toFixed(2)
    if (err instanceof DOMException && err.name === 'AbortError') {
      const timeoutMsg = `${operationLabel} timed out after ${timeoutMs / 1000} seconds.`
      console.error(`[Frontend ExecutionService] [${operationLabel}] Aborted after ${elapsed}s:`, timeoutMsg)
      throw new Error(timeoutMsg)
    }
    console.error(`[Frontend ExecutionService] [${operationLabel}] Request error after ${elapsed}s:`, err)
    throw err
  } finally {
    clearTimeout(timeoutId)
  }
}

/**
 * Trigger Docker sandbox execution for a specific patch.
 */
export async function executePatch(
  repositoryId: string,
  patchId: string,
  request?: SandboxExecutionRequest
): Promise<ApiResponse<SandboxExecution>> {
  return fetchWithTimeout<SandboxExecution>(
    `${API_BASE_URL}/repositories/${repositoryId}/patches/${patchId}/execute`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(request || {}),
    },
    180000,
    'Execute Patch in Docker Sandbox'
  )
}

/**
 * Retrieve status and results for a sandbox execution.
 */
export async function getExecution(
  executionId: string
): Promise<ApiResponse<SandboxExecution>> {
  return fetchWithTimeout<SandboxExecution>(
    `${API_BASE_URL}/executions/${executionId}`,
    {
      method: 'GET',
    },
    15000,
    'Get Sandbox Execution Status'
  )
}

/**
 * Retrieve execution logs.
 */
export async function getExecutionLogs(
  executionId: string
): Promise<ApiResponse<{ execution_id: string; logs: string }>> {
  return fetchWithTimeout<{ execution_id: string; logs: string }>(
    `${API_BASE_URL}/executions/${executionId}/logs`,
    {
      method: 'GET',
    },
    15000,
    'Get Execution Logs'
  )
}

/**
 * Retrieve full execution report.
 */
export async function getExecutionReport(
  executionId: string
): Promise<ApiResponse<ExecutionReportResponse>> {
  return fetchWithTimeout<ExecutionReportResponse>(
    `${API_BASE_URL}/executions/${executionId}/report`,
    {
      method: 'GET',
    },
    15000,
    'Get Execution Report'
  )
}

/**
 * List executions for a specific patch.
 */
export async function listExecutionsForPatch(
  repositoryId: string,
  patchId: string
): Promise<ApiResponse<ExecutionListResponse>> {
  return fetchWithTimeout<ExecutionListResponse>(
    `${API_BASE_URL}/repositories/${repositoryId}/patches/${patchId}/executions`,
    {
      method: 'GET',
    },
    15000,
    'List Patch Executions'
  )
}

/**
 * List all executions for a repository.
 */
export async function listExecutionsForRepository(
  repositoryId: string
): Promise<ApiResponse<ExecutionListResponse>> {
  return fetchWithTimeout<ExecutionListResponse>(
    `${API_BASE_URL}/repositories/${repositoryId}/executions`,
    {
      method: 'GET',
    },
    15000,
    'List Repository Executions'
  )
}

