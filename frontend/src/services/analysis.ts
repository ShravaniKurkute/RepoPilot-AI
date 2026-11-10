import type {
  ApiResponse,
  AnalysisRunStatusResponse,
  AnalyzeFileRequest,
  AnalyzeFunctionRequest,
  CodeIssue,
  IssueCategory,
  IssueListResponse,
  IssueStatus,
} from '../types'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1'

export interface IssueFilterParams {
  severity?: string
  category?: string
  file?: string
  status?: string
  min_confidence?: number
}

export async function runAiAnalysis(
  repositoryId: string,
  categories?: IssueCategory[]
): Promise<ApiResponse<AnalysisRunStatusResponse>> {
  const response = await fetch(`${API_BASE_URL}/repositories/${repositoryId}/ai-analyze`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({ categories: categories ?? null }),
  })

  const payload = await response.json()
  if (!response.ok) {
    throw new Error(
      payload.detail || payload.message || `AI code analysis failed (${response.status})`
    )
  }

  return payload
}

export async function analyzeFile(
  repositoryId: string,
  data: AnalyzeFileRequest
): Promise<ApiResponse<AnalysisRunStatusResponse>> {
  const response = await fetch(`${API_BASE_URL}/repositories/${repositoryId}/ai-analyze/file`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(data),
  })

  const payload = await response.json()
  if (!response.ok) {
    throw new Error(
      payload.detail || payload.message || `File AI analysis failed (${response.status})`
    )
  }

  return payload
}

export async function analyzeFunction(
  repositoryId: string,
  data: AnalyzeFunctionRequest
): Promise<ApiResponse<AnalysisRunStatusResponse>> {
  const response = await fetch(`${API_BASE_URL}/repositories/${repositoryId}/ai-analyze/function`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(data),
  })

  const payload = await response.json()
  if (!response.ok) {
    throw new Error(
      payload.detail || payload.message || `Function AI analysis failed (${response.status})`
    )
  }

  return payload
}

export async function getAnalysisStatus(
  repositoryId: string,
  runId?: string
): Promise<ApiResponse<AnalysisRunStatusResponse>> {
  const query = runId ? `?run_id=${encodeURIComponent(runId)}` : ''
  const response = await fetch(
    `${API_BASE_URL}/repositories/${repositoryId}/ai-analysis/status${query}`,
    {
      headers: {
        Accept: 'application/json',
      },
    }
  )

  const payload = await response.json()
  if (!response.ok) {
    throw new Error(
      payload.detail || payload.message || `Failed to fetch analysis status (${response.status})`
    )
  }

  return payload
}

export async function getIssues(
  repositoryId: string,
  filters?: IssueFilterParams
): Promise<ApiResponse<IssueListResponse>> {
  const query = new URLSearchParams()
  if (filters?.severity) query.set('severity', filters.severity)
  if (filters?.category) query.set('category', filters.category)
  if (filters?.file) query.set('file', filters.file)
  if (filters?.status) query.set('status', filters.status)
  if (filters?.min_confidence !== undefined) query.set('min_confidence', String(filters.min_confidence))

  const qs = query.toString() ? `?${query.toString()}` : ''
  const response = await fetch(`${API_BASE_URL}/repositories/${repositoryId}/issues${qs}`, {
    headers: {
      Accept: 'application/json',
    },
  })

  const payload = await response.json()
  if (!response.ok) {
    throw new Error(
      payload.detail || payload.message || `Failed to fetch code issues (${response.status})`
    )
  }

  return payload
}

export async function getIssue(
  repositoryId: string,
  issueId: string
): Promise<ApiResponse<CodeIssue>> {
  const response = await fetch(
    `${API_BASE_URL}/repositories/${repositoryId}/issues/${encodeURIComponent(issueId)}`,
    {
      headers: {
        Accept: 'application/json',
      },
    }
  )

  const payload = await response.json()
  if (!response.ok) {
    throw new Error(
      payload.detail || payload.message || `Failed to fetch issue detail (${response.status})`
    )
  }

  return payload
}

export async function updateIssueStatus(
  issueId: string,
  status: IssueStatus,
  notes?: string
): Promise<ApiResponse<CodeIssue>> {
  const response = await fetch(`${API_BASE_URL}/issues/${encodeURIComponent(issueId)}/status`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify({ status, notes: notes || null }),
  })

  const payload = await response.json()
  if (!response.ok) {
    throw new Error(
      payload.detail || payload.message || `Failed to update issue status (${response.status})`
    )
  }

  return payload
}

