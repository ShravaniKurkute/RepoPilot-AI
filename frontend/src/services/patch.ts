import type {
  ApiResponse,
  FixPlan,
  PatchProposal,
  PatchProposalListResponse,
  PatchReviewRequest,
  WorkflowStatusResponse,
} from '../types'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1'

/**
 * Executes a fetch request with timeout protection via AbortController and diagnostic boundary logging.
 */
async function fetchWithTimeout<T>(
  url: string,
  options: RequestInit = {},
  timeoutMs: number = 75000,
  operationLabel: string = 'API Request'
): Promise<ApiResponse<T>> {
  const startTime = performance.now()
  console.log(`[Frontend PatchService] [${operationLabel}] Initiating ${options.method || 'GET'} request to ${url} (timeout: ${timeoutMs / 1000}s)`)

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
    console.log(`[Frontend PatchService] [${operationLabel}] Received response from ${url} in ${elapsed}s (status: ${response.status})`)

    let payload: any
    try {
      payload = await response.json()
    } catch {
      payload = { detail: `Server responded with status ${response.status}` }
    }

    if (!response.ok) {
      const errorMsg = payload.detail || payload.message || `${operationLabel} failed (${response.status})`
      console.error(`[Frontend PatchService] [${operationLabel}] HTTP ${response.status} Error:`, errorMsg)
      throw new Error(errorMsg)
    }

    console.log(`[Frontend PatchService] [${operationLabel}] Succeeded in ${elapsed}s`)
    return payload
  } catch (err: unknown) {
    const elapsed = ((performance.now() - startTime) / 1000).toFixed(2)
    if (err instanceof DOMException && err.name === 'AbortError') {
      const timeoutMsg = `${operationLabel} timed out after ${timeoutMs / 1000} seconds. Please check Gemini API status or backend logs.`
      console.error(`[Frontend PatchService] [${operationLabel}] Aborted after ${elapsed}s:`, timeoutMsg)
      throw new Error(timeoutMsg)
    }
    console.error(`[Frontend PatchService] [${operationLabel}] Request error after ${elapsed}s:`, err)
    throw err
  } finally {
    clearTimeout(timeoutId)
  }
}

export async function createFixPlan(
  repositoryId: string,
  issueId: string,
  timeoutMs: number = 75000
): Promise<ApiResponse<FixPlan>> {
  return fetchWithTimeout<FixPlan>(
    `${API_BASE_URL}/repositories/${repositoryId}/issues/${issueId}/fix-plan`,
    {
      method: 'POST',
      headers: {
        Accept: 'application/json',
      },
    },
    timeoutMs,
    'Create Fix Plan'
  )
}

export async function getFixPlan(
  repositoryId: string,
  issueId: string,
  timeoutMs: number = 20000
): Promise<ApiResponse<FixPlan>> {
  return fetchWithTimeout<FixPlan>(
    `${API_BASE_URL}/repositories/${repositoryId}/issues/${issueId}/fix-plan`,
    {
      headers: {
        Accept: 'application/json',
      },
    },
    timeoutMs,
    'Get Fix Plan'
  )
}

export async function generatePatch(
  repositoryId: string,
  issueId: string,
  feedback?: string,
  timeoutMs: number = 90000
): Promise<ApiResponse<PatchProposal>> {
  return fetchWithTimeout<PatchProposal>(
    `${API_BASE_URL}/repositories/${repositoryId}/issues/${issueId}/generate-patch`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({ feedback: feedback || null }),
    },
    timeoutMs,
    'Generate Patch Proposal'
  )
}

export async function listPatches(
  repositoryId: string,
  timeoutMs: number = 20000
): Promise<ApiResponse<PatchProposalListResponse>> {
  return fetchWithTimeout<PatchProposalListResponse>(
    `${API_BASE_URL}/repositories/${repositoryId}/patches`,
    {
      headers: {
        Accept: 'application/json',
      },
    },
    timeoutMs,
    'List Patches'
  )
}

export async function getPatch(
  patchId: string,
  timeoutMs: number = 20000
): Promise<ApiResponse<PatchProposal>> {
  return fetchWithTimeout<PatchProposal>(
    `${API_BASE_URL}/patches/${patchId}`,
    {
      headers: {
        Accept: 'application/json',
      },
    },
    timeoutMs,
    'Get Patch'
  )
}

export async function getPatchDiff(
  patchId: string,
  timeoutMs: number = 20000
): Promise<string> {
  const url = `${API_BASE_URL}/patches/${patchId}/diff`
  const controller = new AbortController()
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const response = await fetch(url, { signal: controller.signal })
    if (!response.ok) {
      throw new Error(`Failed to get patch diff (${response.status})`)
    }
    return await response.text()
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      throw new Error(`Failed to retrieve diff: request timed out after ${timeoutMs / 1000}s`)
    }
    throw err
  } finally {
    clearTimeout(timeoutId)
  }
}

export async function reviewPatch(
  patchId: string,
  review: PatchReviewRequest,
  timeoutMs: number = 30000
): Promise<ApiResponse<PatchProposal>> {
  return fetchWithTimeout<PatchProposal>(
    `${API_BASE_URL}/patches/${patchId}/review`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify(review),
    },
    timeoutMs,
    'Review Patch'
  )
}

export async function regeneratePatch(
  patchId: string,
  feedback?: string,
  timeoutMs: number = 90000
): Promise<ApiResponse<PatchProposal>> {
  return fetchWithTimeout<PatchProposal>(
    `${API_BASE_URL}/patches/${patchId}/regenerate`,
    {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
      },
      body: JSON.stringify({ feedback: feedback || null }),
    },
    timeoutMs,
    'Regenerate Patch'
  )
}

export async function getPatchStatus(
  patchId: string,
  timeoutMs: number = 20000
): Promise<ApiResponse<WorkflowStatusResponse>> {
  return fetchWithTimeout<WorkflowStatusResponse>(
    `${API_BASE_URL}/patches/${patchId}/status`,
    {
      headers: {
        Accept: 'application/json',
      },
    },
    timeoutMs,
    'Get Patch Status'
  )
}
