import React from 'react'
import { Server, Activity, CheckCircle2, AlertTriangle, RefreshCw } from 'lucide-react'
import type { HealthResponse } from '../types'

interface HealthCardProps {
  health: HealthResponse | null
  loading: boolean
  error: string | null
  lastChecked: Date | null
  onRefresh: () => void
}

export const HealthCard: React.FC<HealthCardProps> = ({
  health,
  loading,
  error,
  lastChecked,
  onRefresh,
}) => {
  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-xl p-6 shadow-xl">
      <div className="flex items-center justify-between pb-4 border-b border-slate-800">
        <div className="flex items-center space-x-3">
          <div className="p-2.5 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20">
            <Server className="h-5 w-5" />
          </div>
          <div>
            <h3 className="text-base font-semibold text-slate-100">FastAPI Backend Status</h3>
            <p className="text-xs text-slate-400">Core API & Agent Orchestration Gateway</p>
          </div>
        </div>

        <button
          onClick={onRefresh}
          disabled={loading}
          className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-cyan-400 bg-slate-950 px-3 py-1.5 rounded-md border border-slate-800 transition disabled:opacity-50 cursor-pointer"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
          Refresh
        </button>
      </div>

      <div className="mt-4 grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-slate-950/60 p-3.5 rounded-lg border border-slate-800/80">
          <div className="text-xs text-slate-400 mb-1">Status</div>
          <div className="flex items-center gap-2">
            {health?.status === 'healthy' ? (
              <>
                <CheckCircle2 className="h-4 w-4 text-emerald-400" />
                <span className="text-sm font-semibold text-emerald-400 uppercase tracking-wide">
                  {health.status}
                </span>
              </>
            ) : error ? (
              <>
                <AlertTriangle className="h-4 w-4 text-rose-400" />
                <span className="text-sm font-semibold text-rose-400">Disconnected</span>
              </>
            ) : (
              <span className="text-sm text-slate-400">Checking...</span>
            )}
          </div>
        </div>

        <div className="bg-slate-950/60 p-3.5 rounded-lg border border-slate-800/80">
          <div className="text-xs text-slate-400 mb-1">Environment / Version</div>
          <div className="text-sm font-semibold text-slate-200">
            {health ? (
              <span className="font-mono text-cyan-400">
                {health.environment} (v{health.version})
              </span>
            ) : (
              '—'
            )}
          </div>
        </div>

        <div className="bg-slate-950/60 p-3.5 rounded-lg border border-slate-800/80">
          <div className="text-xs text-slate-400 mb-1">Last Heartbeat</div>
          <div className="text-xs font-mono text-slate-300">
            {lastChecked ? lastChecked.toLocaleTimeString() : 'Pending'}
          </div>
        </div>
      </div>

      {health?.subsystems && (
        <div className="mt-4 pt-4 border-t border-slate-800/60">
          <div className="text-xs font-medium text-slate-400 mb-2.5 flex items-center gap-1.5">
            <Activity className="h-3.5 w-3.5 text-cyan-400" />
            Subsystem Readiness
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
            {Object.entries(health.subsystems).map(([key, value]) => (
              <div
                key={key}
                className="flex items-center justify-between text-xs px-2.5 py-1.5 rounded bg-slate-950/40 border border-slate-800/60"
              >
                <span className="text-slate-400 capitalize">{key.replace('_', ' ')}</span>
                <span className="font-mono text-[11px] text-slate-300">{value}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {error && (
        <div className="mt-4 p-3 rounded-lg bg-rose-950/30 border border-rose-900/60 text-xs text-rose-300">
          Connection Error: {error}. Ensure the FastAPI server is running at{' '}
          <code className="text-rose-200">http://localhost:8000</code>.
        </div>
      )}
    </div>
  )
}
