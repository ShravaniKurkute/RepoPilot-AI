import React from 'react'
import { Terminal, Shield, Cpu } from 'lucide-react'
import type { HealthResponse } from '../types'

interface HeaderProps {
  health: HealthResponse | null
  loading: boolean
}

export const Header: React.FC<HeaderProps> = ({ health, loading }) => {
  const isHealthy = health?.status === 'healthy'

  return (
    <header className="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="h-10 w-10 rounded-xl bg-gradient-to-tr from-cyan-500 to-blue-600 flex items-center justify-center text-white shadow-lg shadow-cyan-500/20">
            <Terminal className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <span className="font-bold text-lg text-slate-100 tracking-tight">RepoPilot AI</span>
              <span className="text-[10px] font-semibold tracking-wider uppercase px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800/60">
                Autonomous Engineer
              </span>
            </div>
            <p className="text-xs text-slate-400">Autonomous Codebase Analysis, Repair & Verification</p>
          </div>
        </div>

        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2 text-xs bg-slate-950/60 border border-slate-800 px-3 py-1.5 rounded-lg">
            <Cpu className="h-4 w-4 text-slate-400" />
            <span className="text-slate-400">Sandbox:</span>
            <span className="text-emerald-400 font-mono font-medium flex items-center gap-1">
              <Shield className="h-3 w-3" /> Docker Isolated
            </span>
          </div>

          <div className="flex items-center space-x-2 text-xs bg-slate-950/60 border border-slate-800 px-3 py-1.5 rounded-lg">
            <span className="text-slate-400">Backend API:</span>
            {loading ? (
              <span className="text-amber-400 animate-pulse">Connecting...</span>
            ) : isHealthy ? (
              <span className="flex items-center text-emerald-400 font-medium">
                <span className="h-2 w-2 rounded-full bg-emerald-500 mr-1.5 animate-ping" />
                Live (v{health?.version})
              </span>
            ) : (
              <span className="flex items-center text-rose-400 font-medium">
                <span className="h-2 w-2 rounded-full bg-rose-500 mr-1.5" />
                Offline
              </span>
            )}
          </div>
        </div>
      </div>
    </header>
  )
}
