import type { HealthResponse } from '../types'

const API_BASE_URL = import.meta.env.VITE_API_URL || '/api/v1'

export async function fetchHealth(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/health`, {
    headers: {
      'Accept': 'application/json',
    },
  })

  if (!response.ok) {
    throw new Error(`Health check failed with status ${response.status}`)
  }

  return response.json()
}
