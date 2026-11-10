import React from 'react'
import { FolderGit2, FileCode, FolderTree, HardDrive, Calendar, GitBranch, ExternalLink } from 'lucide-react'
import type { RepositoryDetail } from '../types'

interface RepositoryCardProps {
  repository: RepositoryDetail
}

const LANGUAGE_COLORS: Record<string, string> = {
  Python: 'bg-blue-500',
  TypeScript: 'bg-indigo-500',
  JavaScript: 'bg-yellow-400',
  Java: 'bg-amber-600',
  'C++': 'bg-pink-500',
  C: 'bg-slate-400',
  Go: 'bg-cyan-400',
  Rust: 'bg-orange-500',
  PHP: 'bg-purple-500',
  Ruby: 'bg-rose-500',
  HTML: 'bg-orange-600',
  CSS: 'bg-sky-500',
  JSON: 'bg-emerald-500',
  Markdown: 'bg-slate-500',
  SQL: 'bg-teal-500',
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`
}

export const RepositoryCard: React.FC<RepositoryCardProps> = ({ repository }) => {
  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
      {/* Header Info */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div className="flex items-center space-x-3.5">
          <div className="h-11 w-11 rounded-xl bg-gradient-to-tr from-cyan-500/20 to-blue-500/20 text-cyan-400 border border-cyan-500/30 flex items-center justify-center shrink-0">
            <FolderGit2 className="h-6 w-6" />
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-lg font-bold text-slate-100 tracking-tight">
                {repository.name}
              </h3>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800/60 uppercase">
                {repository.source_type}
              </span>
              {repository.default_branch && (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-950 text-slate-300 border border-slate-800 flex items-center gap-1">
                  <GitBranch className="h-3 w-3 text-cyan-400" />
                  {repository.default_branch}
                </span>
              )}
            </div>
            {repository.remote_url && (
              <a
                href={repository.remote_url}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-slate-400 hover:text-cyan-400 mt-1 inline-flex items-center gap-1 transition"
              >
                <span>{repository.remote_url}</span>
                <ExternalLink className="h-3 w-3" />
              </a>
            )}
          </div>
        </div>

        <div className="flex items-center gap-2 self-start sm:self-auto text-xs text-slate-400 bg-slate-950 px-3 py-1.5 rounded-lg border border-slate-800">
          <Calendar className="h-3.5 w-3.5 text-slate-500" />
          <span>Ingested: {new Date(repository.created_at).toLocaleString()}</span>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="bg-slate-950/60 p-3.5 rounded-xl border border-slate-800/80 flex items-center space-x-3">
          <div className="p-2 rounded-lg bg-blue-500/10 text-blue-400 border border-blue-500/20">
            <FileCode className="h-4 w-4" />
          </div>
          <div>
            <div className="text-xs text-slate-400">Total Files</div>
            <div className="text-base font-bold text-slate-100 font-mono">
              {repository.total_files.toLocaleString()}
            </div>
          </div>
        </div>

        <div className="bg-slate-950/60 p-3.5 rounded-xl border border-slate-800/80 flex items-center space-x-3">
          <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <FolderTree className="h-4 w-4" />
          </div>
          <div>
            <div className="text-xs text-slate-400">Directories</div>
            <div className="text-base font-bold text-slate-100 font-mono">
              {repository.total_directories.toLocaleString()}
            </div>
          </div>
        </div>

        <div className="bg-slate-950/60 p-3.5 rounded-xl border border-slate-800/80 flex items-center space-x-3">
          <div className="p-2 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <HardDrive className="h-4 w-4" />
          </div>
          <div>
            <div className="text-xs text-slate-400">Total Code Volume</div>
            <div className="text-base font-bold text-slate-100 font-mono">
              {formatBytes(repository.total_size_bytes)}
            </div>
          </div>
        </div>
      </div>

      {/* Programming Languages Breakdown */}
      <div>
        <div className="flex items-center justify-between text-xs mb-2">
          <span className="font-semibold text-slate-200">Programming Languages</span>
          <span className="text-slate-400">{repository.languages.length} identified</span>
        </div>

        {/* Progress bar */}
        {repository.languages.length > 0 ? (
          <>
            <div className="h-2.5 w-full rounded-full bg-slate-950 overflow-hidden flex border border-slate-800">
              {repository.languages.map((lang) => (
                <div
                  key={lang.name}
                  style={{ width: `${lang.percentage}%` }}
                  title={`${lang.name}: ${lang.percentage}% (${formatBytes(lang.byte_count)})`}
                  className={`${LANGUAGE_COLORS[lang.name] || 'bg-slate-500'} transition-all`}
                />
              ))}
            </div>

            <div className="mt-3 flex flex-wrap gap-2">
              {repository.languages.map((lang) => (
                <div
                  key={lang.name}
                  className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-slate-950/80 border border-slate-800/80 text-xs"
                >
                  <span
                    className={`h-2 w-2 rounded-full ${
                      LANGUAGE_COLORS[lang.name] || 'bg-slate-500'
                    }`}
                  />
                  <span className="font-medium text-slate-200">{lang.name}</span>
                  <span className="text-slate-400 text-[11px] font-mono">
                    {lang.percentage}%
                  </span>
                  <span className="text-slate-500 text-[10px]">
                    ({lang.file_count} {lang.file_count === 1 ? 'file' : 'files'})
                  </span>
                </div>
              ))}
            </div>
          </>
        ) : (
          <p className="text-xs text-slate-500 italic">No source code files identified.</p>
        )}
      </div>
    </div>
  )
}

