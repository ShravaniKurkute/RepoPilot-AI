import React from 'react'
import { History, FolderGit2, Calendar, FileText, ChevronRight } from 'lucide-react'
import type { RepositorySummary } from '../types'

interface RecentRepositoriesProps {
  repositories: RepositorySummary[]
  activeRepoId: string | null
  onSelectRepo: (id: string) => void
  loading: boolean
}

export const RecentRepositories: React.FC<RecentRepositoriesProps> = ({
  repositories,
  activeRepoId,
  onSelectRepo,
  loading,
}) => {
  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl">
      <div className="flex items-center justify-between pb-4 border-b border-slate-800">
        <div className="flex items-center space-x-2.5">
          <History className="h-4 w-4 text-cyan-400" />
          <h3 className="text-base font-bold text-slate-100">Ingested Repositories</h3>
        </div>
        <span className="text-xs text-slate-400 font-mono">
          {repositories.length} {repositories.length === 1 ? 'repository' : 'repositories'}
        </span>
      </div>

      <div className="mt-4 space-y-2 max-h-[300px] overflow-y-auto pr-1">
        {loading && repositories.length === 0 ? (
          <p className="text-xs text-slate-500 py-4 text-center">Loading repositories...</p>
        ) : repositories.length === 0 ? (
          <p className="text-xs text-slate-500 py-6 text-center">
            No repositories ingested yet. Use the upload or clone tools above to get started.
          </p>
        ) : (
          repositories.map((repo) => {
            const isActive = repo.id === activeRepoId
            return (
              <div
                key={repo.id}
                onClick={() => onSelectRepo(repo.id)}
                className={`p-3 rounded-xl border transition cursor-pointer flex items-center justify-between ${
                  isActive
                    ? 'bg-cyan-950/30 border-cyan-500/60 shadow-md shadow-cyan-950/20'
                    : 'bg-slate-950/40 border-slate-800/80 hover:border-slate-700 hover:bg-slate-950/70'
                }`}
              >
                <div className="flex items-center space-x-3 overflow-hidden">
                  <div
                    className={`p-2 rounded-lg shrink-0 ${
                      isActive
                        ? 'bg-cyan-500 text-slate-950 font-bold'
                        : 'bg-slate-900 text-slate-400 border border-slate-800'
                    }`}
                  >
                    <FolderGit2 className="h-4 w-4" />
                  </div>

                  <div className="overflow-hidden">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-slate-200 truncate">
                        {repo.name}
                      </span>
                      <span className="text-[10px] px-1.5 py-0.2 rounded uppercase font-mono bg-slate-900 text-cyan-400 border border-slate-800">
                        {repo.source_type}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-[11px] text-slate-500 mt-0.5">
                      <span className="flex items-center gap-1">
                        <FileText className="h-3 w-3" />
                        {repo.total_files} files
                      </span>
                      <span className="flex items-center gap-1">
                        <Calendar className="h-3 w-3" />
                        {new Date(repo.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                </div>

                <ChevronRight
                  className={`h-4 w-4 shrink-0 transition ${
                    isActive ? 'text-cyan-400 translate-x-0.5' : 'text-slate-600'
                  }`}
                />
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

