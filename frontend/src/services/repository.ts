import type {
  ApiResponse,
  RepositoryDetail,
  RepositorySummary,
  RepositoryTreeResponse,
} from '../types'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1'

export async function uploadRepository(file: File): Promise<ApiResponse<RepositoryDetail>> {
  const formData = new FormData()
  formData.append('file', file)

  const response = await fetch(`${API_BASE_URL}/repositories/upload`, {
    method: 'POST',
    body: formData,
  })

  const payload = await response.json()
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `Upload failed (${response.status})`)
  }

  return payload
}

export async function cloneRepository(
  url: string,
  branch?: string
): Promise<ApiResponse<RepositoryDetail>> {
  const response = await fetch(`${API_BASE_URL}/repositories/clone`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      url,
      branch: branch ? branch.trim() : null,
    }),
  })

  const payload = await response.json()
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `Git clone failed (${response.status})`)
  }

  return payload
}

export async function listRepositories(): Promise<ApiResponse<RepositorySummary[]>> {
  const response = await fetch(`${API_BASE_URL}/repositories`, {
    headers: {
      Accept: 'application/json',
    },
  })

  const payload = await response.json()
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `Failed to fetch repositories (${response.status})`)
  }

  return payload
}

export async function getRepositoryDetails(
  repositoryId: string
): Promise<ApiResponse<RepositoryDetail>> {
  const response = await fetch(`${API_BASE_URL}/repositories/${repositoryId}`, {
    headers: {
      Accept: 'application/json',
    },
  })

  const payload = await response.json()
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `Failed to fetch repository (${response.status})`)
  }

  return payload
}

export async function getRepositoryTree(
  repositoryId: string
): Promise<ApiResponse<RepositoryTreeResponse>> {
  const response = await fetch(`${API_BASE_URL}/repositories/${repositoryId}/tree`, {
    headers: {
      Accept: 'application/json',
    },
  })

  const payload = await response.json()
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `Failed to fetch tree (${response.status})`)
  }

  return payload
}

