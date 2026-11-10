import type {
  ApiResponse,
  CallGraphEdge,
  FileAnalysisResult,
  FileDependency,
  RepositoryAnalysisResponse,
  Symbol,
} from '../types'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1'

export async function analyzeRepository(
  repositoryId: string
): Promise<ApiResponse<RepositoryAnalysisResponse>> {
  const response = await fetch(`${API_BASE_URL}/repositories/${repositoryId}/analyze`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
    },
  })

  const payload = await response.json()
  if (!response.ok) {
    throw new Error(
      payload.detail || payload.message || `Code intelligence analysis failed (${response.status})`
    )
  }

  return payload
}

export async function getAnalysis(
  repositoryId: string
): Promise<ApiResponse<RepositoryAnalysisResponse>> {
  const response = await fetch(`${API_BASE_URL}/repositories/${repositoryId}/analysis`, {
    headers: {
      Accept: 'application/json',
    },
  })

  const payload = await response.json()
  if (!response.ok) {
    throw new Error(
      payload.detail || payload.message || `Failed to fetch analysis (${response.status})`
    )
  }

  return payload
}

export async function getSymbols(
  repositoryId: string,
  params?: { name?: string; type?: string; file?: string }
): Promise<ApiResponse<Symbol[]>> {
  const query = new URLSearchParams()
  if (params?.name) query.set('name', params.name)
  if (params?.type) query.set('type', params.type)
  if (params?.file) query.set('file', params.file)

  const qs = query.toString() ? `?${query.toString()}` : ''
  const response = await fetch(`${API_BASE_URL}/repositories/${repositoryId}/symbols${qs}`, {
    headers: {
      Accept: 'application/json',
    },
  })

  const payload = await response.json()
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `Failed to fetch symbols (${response.status})`)
  }

  return payload
}

export async function getDependencies(
  repositoryId: string
): Promise<ApiResponse<Record<string, FileDependency>>> {
  const response = await fetch(`${API_BASE_URL}/repositories/${repositoryId}/dependencies`, {
    headers: {
      Accept: 'application/json',
    },
  })

  const payload = await response.json()
  if (!response.ok) {
    throw new Error(
      payload.detail || payload.message || `Failed to fetch dependencies (${response.status})`
    )
  }

  return payload
}

export async function getCallGraph(
  repositoryId: string
): Promise<ApiResponse<CallGraphEdge[]>> {
  const response = await fetch(`${API_BASE_URL}/repositories/${repositoryId}/call-graph`, {
    headers: {
      Accept: 'application/json',
    },
  })

  const payload = await response.json()
  if (!response.ok) {
    throw new Error(
      payload.detail || payload.message || `Failed to fetch call graph (${response.status})`
    )
  }

  return payload
}

export async function getFileAnalysis(
  repositoryId: string,
  filePath: string
): Promise<ApiResponse<FileAnalysisResult>> {
  const cleanPath = filePath.replace(/^\/+/, '')
  const response = await fetch(
    `${API_BASE_URL}/repositories/${repositoryId}/files/${cleanPath}/analysis`,
    {
      headers: {
        Accept: 'application/json',
      },
    }
  )

  const payload = await response.json()
  if (!response.ok) {
    throw new Error(
      payload.detail || payload.message || `Failed to fetch file analysis (${response.status})`
    )
  }

  return payload
}

