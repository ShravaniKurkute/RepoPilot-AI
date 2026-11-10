import { useState, useEffect, useCallback } from 'react'
import type { HealthResponse } from '../types'
import { fetchHealth } from '../services/api'

export function useHealth(pollIntervalMs: number = 10000) {
  const [data, setData] = useState<HealthResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [lastChecked, setLastChecked] = useState<Date | null>(null)

  const checkHealth = useCallback(async (isManual: boolean = false) => {
    if (isManual) {
      setLoading(true)
    }
    try {
      const res = await fetchHealth()
      setData(res)
      setError(null)
      setLastChecked(new Date())
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to connect to backend')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    let ignore = false

    async function initialFetch() {
      try {
        const res = await fetchHealth()
        if (!ignore) {
          setData(res)
          setError(null)
          setLastChecked(new Date())
        }
      } catch (err: unknown) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : 'Failed to connect to backend')
          setData(null)
        }
      } finally {
        if (!ignore) {
          setLoading(false)
        }
      }
    }

    initialFetch()

    const timer = setInterval(() => {
      checkHealth(false)
    }, pollIntervalMs)

    return () => {
      ignore = true
      clearInterval(timer)
    }
  }, [checkHealth, pollIntervalMs])

  const refetch = useCallback(() => checkHealth(true), [checkHealth])

  return { data, loading, error, lastChecked, refetch }
}
