import type {
  ApiResponse,
  IndexingStatsResponse,
  IndexingStatusResponse,
  SearchQuery,
  SearchResponse,
} from '../types'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1'

export async function indexRepository(
  repositoryId: string,
  force: boolean = false
): Promise<ApiResponse<IndexingStatusResponse>> {
  const url = `${API_BASE_URL}/repositories/${repositoryId}/index${force ? '?force=true' : ''}`
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
    },
  })

  const payload = await response.json()
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `Indexing failed (${response.status})`)
  }

  return payload
}

export async function getIndexStatus(
  repositoryId: string
): Promise<ApiResponse<IndexingStatusResponse>> {
  const response = await fetch(`${API_BASE_URL}/repositories/${repositoryId}/index/status`, {
    headers: {
      Accept: 'application/json',
    },
  })

  const payload = await response.json()
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `Failed to fetch status (${response.status})`)
  }

  return payload
}

export async function getIndexStats(
  repositoryId: string
): Promise<ApiResponse<IndexingStatsResponse>> {
  const response = await fetch(`${API_BASE_URL}/repositories/${repositoryId}/index/stats`, {
    headers: {
      Accept: 'application/json',
    },
  })

  const payload = await response.json()
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `Failed to fetch stats (${response.status})`)
  }

  return payload
}

export async function searchCodebase(
  repositoryId: string,
  query: SearchQuery
): Promise<ApiResponse<SearchResponse>> {
  const response = await fetch(`${API_BASE_URL}/repositories/${repositoryId}/search`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Accept: 'application/json',
    },
    body: JSON.stringify(query),
  })

  const payload = await response.json()
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `Search failed (${response.status})`)
  }

  return payload
}

export async function deleteIndex(
  repositoryId: string
): Promise<ApiResponse<{ repository_id: string; deleted: boolean }>> {
  const response = await fetch(`${API_BASE_URL}/repositories/${repositoryId}/index`, {
    method: 'DELETE',
    headers: {
      Accept: 'application/json',
    },
  })

  const payload = await response.json()
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `Failed to delete index (${response.status})`)
  }

  return payload
}

