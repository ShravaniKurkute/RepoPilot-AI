import React, { useState, useEffect } from 'react'
import {
  Search,
  Sparkles,
  Check,
  Copy,
  AlertCircle,
  RefreshCw,
  FileCode2,
} from 'lucide-react'
import type {
  IndexingStatsResponse,
  IndexingStatusResponse,
  SearchQuery,
  SearchResponse,
  SearchResultChunk,
} from '../types'
import {
  getIndexStats,
  getIndexStatus,
  indexRepository,
  searchCodebase,
} from '../services/rag'

interface CodeSearchSectionProps {
  repositoryId: string
  repositoryName: string
}

export const CodeSearchSection: React.FC<CodeSearchSectionProps> = ({
  repositoryId,
  repositoryName,
}) => {
  const [query, setQuery] = useState<string>('')
  const [searchMode, setSearchMode] = useState<'hybrid' | 'semantic' | 'keyword'>('hybrid')
  const [topK, setTopK] = useState<number>(10)

  const [searching, setSearching] = useState<boolean>(false)
  const [indexing, setIndexing] = useState<boolean>(false)
  const [status, setStatus] = useState<IndexingStatusResponse | null>(null)
  const [stats, setStats] = useState<IndexingStatsResponse | null>(null)
  const [searchResponse, setSearchResponse] = useState<SearchResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [copiedId, setCopiedId] = useState<string | null>(null)

  // Fetch indexing info when repository changes
  useEffect(() => {
    let ignore = false
    async function loadInfo() {
      try {
        const [statusRes, statsRes] = await Promise.allSettled([
          getIndexStatus(repositoryId),
          getIndexStats(repositoryId),
        ])

        if (!ignore) {
          if (statusRes.status === 'fulfilled') setStatus(statusRes.value.data)
          if (statsRes.status === 'fulfilled') setStats(statsRes.value.data)
          setSearchResponse(null)
          setError(null)
        }
      } catch {
        if (!ignore) {
          setSearchResponse(null)
          setError(null)
        }
      }
    }

    loadInfo()

    return () => {
      ignore = true
    }
  }, [repositoryId])

  const handleIndex = async (force: boolean = false) => {
    setIndexing(true)
    setError(null)
    try {
      const res = await indexRepository(repositoryId, force)
      setStatus(res.data)
      const statsRes = await getIndexStats(repositoryId)
      setStats(statsRes.data)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Indexing failed'
      setError(msg)
    } finally {
      setIndexing(false)
    }
  }

  const handleSearch = async (e?: React.FormEvent) => {
    if (e) e.preventDefault()
    if (!query.trim()) return

    setSearching(true)
    setError(null)
    try {
      const payload: SearchQuery = {
        query: query.trim(),
        top_k: topK,
        search_mode: searchMode,
      }
      const res = await searchCodebase(repositoryId, payload)
      setSearchResponse(res.data)

      // Refresh index stats if it auto-indexed
      if (!stats || stats.total_chunks === 0) {
        const updatedStats = await getIndexStats(repositoryId)
        setStats(updatedStats.data)
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Search failed'
      setError(msg)
    } finally {
      setSearching(false)
    }
  }

  const handleCopy = (chunkId: string, text: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(chunkId)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const isIndexed = Boolean(stats && stats.total_chunks > 0)


  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div className="flex items-center space-x-3.5">
          <div className="h-11 w-11 rounded-xl bg-gradient-to-tr from-purple-500/20 to-cyan-500/20 text-purple-400 border border-purple-500/30 flex items-center justify-center shrink-0">
            <Sparkles className="h-6 w-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-bold text-slate-100 tracking-tight">
                Repository-Aware Code RAG
              </h3>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-purple-950 text-purple-400 border border-purple-800/60 uppercase">
                Phase 3
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Hybrid retrieval combining pgvector dense embeddings with lexical keyword matching & RRF fusion.
            </p>
          </div>
        </div>

        {/* Index Action Button */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleIndex(isIndexed)}
            disabled={indexing}
            className="inline-flex items-center gap-2 px-3.5 py-1.5 text-xs font-semibold rounded-xl text-slate-200 bg-slate-800 hover:bg-slate-700 border border-slate-700 transition disabled:opacity-60 cursor-pointer disabled:cursor-not-allowed"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${indexing ? 'animate-spin' : ''}`} />
            <span>{indexing ? 'Indexing Codebase...' : isIndexed ? 'Re-index Code' : 'Index Repository'}</span>
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800/60 text-xs text-rose-300 flex items-start gap-3">
          <AlertCircle className="h-4 w-4 shrink-0 text-rose-400 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {/* Index Status Metrics Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-slate-950/60 p-3.5 rounded-xl border border-slate-800/80">
        <div>
          <span className="text-[11px] text-slate-400 block">Vector Index Status</span>
          <div className="flex items-center gap-1.5 mt-0.5">
            {isIndexed ? (
              <>
                <span className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
                <span className="text-xs font-semibold text-emerald-400">
                  {status?.status === 'completed' ? 'Indexed & Ready' : status?.status || 'Indexed & Ready'}
                </span>
              </>
            ) : (
              <>
                <span className="h-2 w-2 rounded-full bg-amber-400" />
                <span className="text-xs font-semibold text-amber-400">
                  {status?.status === 'indexing' ? 'Indexing...' : 'Not Indexed'}
                </span>
              </>
            )}
          </div>
        </div>

        <div>
          <span className="text-[11px] text-slate-400 block">Indexed Chunks</span>
          <span className="text-xs font-bold font-mono text-slate-200 mt-0.5 block">
            {stats?.total_chunks.toLocaleString() || 0} chunks ({stats?.total_files || 0} files)
          </span>
        </div>

        <div>
          <span className="text-[11px] text-slate-400 block">Embedding Dimension</span>
          <span className="text-xs font-bold font-mono text-indigo-300 mt-0.5 block">
            {stats?.embedding_dimension || 768} dims • {stats?.embedding_model || 'text-embedding-004'}
          </span>
        </div>

        <div>
          <span className="text-[11px] text-slate-400 block">Named Symbols Captured</span>
          <span className="text-xs font-bold font-mono text-cyan-300 mt-0.5 block">
            {stats?.total_symbols_indexed.toLocaleString() || 0} symbols
          </span>
        </div>
      </div>

      {/* Search Input Form */}
      <form onSubmit={handleSearch} className="space-y-3">
        <div className="relative">
          <Search className="absolute left-3.5 top-3.5 h-4 w-4 text-slate-400" />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search code semantics, functions, classes, auth logic, or SQL queries..."
            className="w-full pl-10 pr-28 py-3 bg-slate-950 border border-slate-700/80 rounded-xl text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500/60 shadow-inner"
          />
          <button
            type="submit"
            disabled={searching || !query.trim()}
            className="absolute right-2 top-2 px-4 py-1.5 text-xs font-semibold rounded-lg bg-gradient-to-r from-cyan-400 to-indigo-400 text-slate-950 hover:from-cyan-300 hover:to-indigo-300 transition disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed"
          >
            {searching ? 'Searching...' : 'Search Code'}
          </button>
        </div>

        {/* Search Controls */}
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2">
            <span className="text-slate-400 font-medium">Retrieval Mode:</span>
            <div className="flex items-center gap-1 bg-slate-950 p-1 rounded-lg border border-slate-800">
              <button
                type="button"
                onClick={() => setSearchMode('hybrid')}
                className={`px-2.5 py-1 rounded-md transition ${
                  searchMode === 'hybrid'
                    ? 'bg-gradient-to-r from-cyan-500/20 to-indigo-500/20 text-cyan-300 border border-cyan-500/30'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Hybrid (RRF)
              </button>
              <button
                type="button"
                onClick={() => setSearchMode('semantic')}
                className={`px-2.5 py-1 rounded-md transition ${
                  searchMode === 'semantic'
                    ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Semantic
              </button>
              <button
                type="button"
                onClick={() => setSearchMode('keyword')}
                className={`px-2.5 py-1 rounded-md transition ${
                  searchMode === 'keyword'
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                Keyword
              </button>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-slate-400">Top Results:</span>
            <select
              value={topK}
              onChange={(e) => setTopK(Number(e.target.value))}
              className="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1 text-slate-300 font-mono focus:outline-none focus:border-cyan-500"
            >
              <option value={5}>Top 5</option>
              <option value={10}>Top 10</option>
              <option value={20}>Top 20</option>
            </select>
          </div>
        </div>
      </form>

      {/* Search Results Display */}
      {searching ? (
        <div className="py-12 text-center text-slate-400 text-xs animate-pulse space-y-2">
          <div className="h-8 w-8 mx-auto rounded-full border-2 border-cyan-400 border-t-transparent animate-spin" />
          <p>Querying pgvector & executing Reciprocal Rank Fusion...</p>
        </div>
      ) : searchResponse ? (
        <div className="space-y-4">
          <div className="flex items-center justify-between text-xs text-slate-400 pb-2 border-b border-slate-800">
            <span>
              Retrieved <strong className="text-slate-200">{searchResponse.total_results}</strong> results for &ldquo;{searchResponse.query}&rdquo;
            </span>
            <span className="font-mono text-[11px] uppercase bg-slate-950 px-2 py-0.5 rounded border border-slate-800 text-cyan-400">
              Mode: {searchResponse.search_mode}
            </span>
          </div>

          {searchResponse.results.length === 0 ? (
            <div className="py-10 text-center rounded-xl bg-slate-950/40 border border-slate-800 text-slate-400 text-xs">
              No code snippets matched your query. Try different keywords or switch search modes.
            </div>
          ) : (
            <div className="space-y-4">
              {searchResponse.results.map((res: SearchResultChunk, index: number) => {
                const percentage = Math.round(res.relevance_score * 100)
                return (
                  <div
                    key={res.chunk_id || index}
                    className="bg-slate-950/80 border border-slate-800 rounded-xl overflow-hidden shadow-lg transition hover:border-slate-700"
                  >
                    {/* Result Header */}
                    <div className="bg-slate-900/70 px-4 py-2.5 border-b border-slate-800 flex flex-wrap items-center justify-between gap-2">
                      <div className="flex items-center gap-2 flex-wrap text-xs">
                        <FileCode2 className="h-4 w-4 text-cyan-400 shrink-0" />
                        <span className="font-mono font-medium text-slate-200">
                          {res.file_path}:{res.start_line}-{res.end_line}
                        </span>

                        {res.symbol_name && (
                          <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-indigo-950 text-indigo-300 border border-indigo-800/60">
                            {res.symbol_type ? `${res.symbol_type}: ` : ''}{res.symbol_name}
                          </span>
                        )}

                        <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-slate-900 text-slate-400 border border-slate-800">
                          {res.language}
                        </span>
                      </div>

                      <div className="flex items-center gap-3">
                        {/* Retrieval method badge */}
                        <span
                          className={`text-[10px] font-semibold px-2 py-0.5 rounded-full uppercase border ${
                            res.retrieval_method === 'hybrid'
                              ? 'bg-gradient-to-r from-cyan-950 to-indigo-950 text-cyan-300 border-cyan-800/60'
                              : res.retrieval_method === 'semantic'
                              ? 'bg-purple-950 text-purple-300 border-purple-800/60'
                              : 'bg-slate-900 text-amber-300 border-amber-800/60'
                          }`}
                        >
                          {res.retrieval_method}
                        </span>

                        {/* Relevance Bar */}
                        <div className="flex items-center gap-1.5">
                          <div className="w-16 h-1.5 bg-slate-800 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-gradient-to-r from-cyan-400 to-indigo-400 rounded-full"
                              style={{ width: `${percentage}%` }}
                            />
                          </div>
                          <span className="text-[11px] font-mono font-semibold text-slate-300">
                            {percentage}%
                          </span>
                        </div>

                        {/* Copy Code Button */}
                        <button
                          onClick={() => handleCopy(res.chunk_id, res.content)}
                          className="p-1 rounded text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition"
                          title="Copy snippet"
                        >
                          {copiedId === res.chunk_id ? (
                            <Check className="h-3.5 w-3.5 text-emerald-400" />
                          ) : (
                            <Copy className="h-3.5 w-3.5" />
                          )}
                        </button>
                      </div>
                    </div>

                    {/* Code Snippet Content */}
                    <div className="p-3 bg-slate-950 overflow-x-auto text-xs font-mono text-slate-300 leading-relaxed max-h-64">
                      <pre>
                        <code>{res.content}</code>
                      </pre>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      ) : (
        <div className="py-8 text-center text-slate-500 text-xs space-y-1">
          <p>Enter a query above to retrieve relevant code across {repositoryName}.</p>
          <p className="text-[11px] text-slate-600">
            Supports natural language questions like &ldquo;where is user authentication handled?&rdquo; or exact identifiers.
          </p>
        </div>
      )}
    </div>
  )
}
