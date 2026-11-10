import React from 'react'
import { CheckCircle2, Clock, CircleDot } from 'lucide-react'
import type { RoadmapPhase } from '../types'

interface RoadmapCardProps {
  phase: RoadmapPhase
}

export const RoadmapCard: React.FC<RoadmapCardProps> = ({ phase }) => {
  const isDone = phase.status === 'completed'
  const isCurrent = phase.status === 'in-progress'

  return (
    <div
      className={`rounded-xl p-5 border transition ${
        isCurrent
          ? 'bg-cyan-950/20 border-cyan-500/40 shadow-lg shadow-cyan-950/30'
          : isDone
          ? 'bg-slate-900/60 border-emerald-900/40'
          : 'bg-slate-900/40 border-slate-800/80 opacity-75'
      }`}
    >
      <div className="flex items-start justify-between">
        <div className="flex items-center space-x-2">
          {isDone ? (
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
          ) : isCurrent ? (
            <CircleDot className="h-4 w-4 text-cyan-400 animate-pulse" />
          ) : (
            <Clock className="h-4 w-4 text-slate-500" />
          )}
          <span className="text-xs font-mono font-medium text-slate-400">
            Phase {phase.id}
          </span>
        </div>
        <span
          className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full ${
            isDone
              ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/40'
              : isCurrent
              ? 'bg-cyan-950 text-cyan-400 border border-cyan-800/40'
              : 'bg-slate-800 text-slate-400 border border-slate-700/40'
          }`}
        >
          {phase.status}
        </span>
      </div>

      <h4 className="mt-2.5 text-sm font-semibold text-slate-100">{phase.title}</h4>
      <p className="mt-1 text-xs text-slate-400 leading-relaxed">{phase.description}</p>
      
      <div className="mt-3 pt-3 border-t border-slate-800/60 flex items-center justify-between text-[11px]">
        <span className="text-slate-500">Focus:</span>
        <span className="font-mono text-slate-300">{phase.tag}</span>
      </div>
    </div>
  )
}
