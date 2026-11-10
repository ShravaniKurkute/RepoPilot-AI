import React, { useState, useEffect, useMemo } from 'react'
import {
  Code2,
  Network,
  GitFork,
  AlertTriangle,
  CheckCircle2,
  Search,
  RefreshCw,
  FileText,
  ArrowRight,
  CornerDownRight,
  Box,
  Layers,
  Terminal,
} from 'lucide-react'
import type {
  RepositoryAnalysisResponse,
  Symbol,
} from '../types'
import { analyzeRepository, getAnalysis } from '../services/codeAnalysis'

interface CodeIntelligenceSectionProps {
  repositoryId: string
  repositoryName: string
}

type TabType = 'overview' | 'symbols' | 'dependencies' | 'callgraph' | 'inspector'

export const CodeIntelligenceSection: React.FC<CodeIntelligenceSectionProps> = ({
  repositoryId,
  repositoryName,
}) => {
  const [analysis, setAnalysis] = useState<RepositoryAnalysisResponse | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [analyzing, setAnalyzing] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<TabType>('overview')

  // Symbol explorer filters
  const [symbolSearch, setSymbolSearch] = useState<string>('')
  const [symbolTypeFilter, setSymbolTypeFilter] = useState<string>('all')

  // File inspector selection
  const [selectedFilePath, setSelectedFilePath] = useState<string>('')

  // Load existing analysis on repository change
  useEffect(() => {
    let ignore = false
    async function loadAnalysis() {
      setLoading(true)
      setError(null)
      try {
        const res = await getAnalysis(repositoryId)
        if (!ignore) {
          setAnalysis(res.data)
          if (res.data.files && Object.keys(res.data.files).length > 0) {
            setSelectedFilePath(Object.keys(res.data.files)[0])
          }
        }
      } catch {
        // Analysis not created yet for this repo
        if (!ignore) {
          setAnalysis(null)
        }
      } finally {
        if (!ignore) {
          setLoading(false)
        }
      }
    }

    loadAnalysis()

    return () => {
      ignore = true
    }
  }, [repositoryId])

  const handleRunAnalysis = async () => {
    setAnalyzing(true)
    setError(null)
    try {
      const res = await analyzeRepository(repositoryId)
      setAnalysis(res.data)
      if (res.data.files && Object.keys(res.data.files).length > 0) {
        setSelectedFilePath(Object.keys(res.data.files)[0])
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Analysis failed'
      setError(msg)
    } finally {
      setAnalyzing(false)
    }
  }

  // Filtered symbols
  const filteredSymbols = useMemo(() => {
    if (!analysis) return []
    return analysis.symbols.filter((s: Symbol) => {
      const matchesSearch =
        symbolSearch === '' ||
        s.name.toLowerCase().includes(symbolSearch.toLowerCase()) ||
        s.file_path.toLowerCase().includes(symbolSearch.toLowerCase())

      const matchesType =
        symbolTypeFilter === 'all' ||
        s.symbol_type.toLowerCase() === symbolTypeFilter.toLowerCase()

      return matchesSearch && matchesType
    })
  }, [analysis, symbolSearch, symbolTypeFilter])

  // Selected file details for inspector
  const selectedFileAnalysis = useMemo(() => {
    if (!analysis || !selectedFilePath) return null
    return analysis.files[selectedFilePath] || null
  }, [analysis, selectedFilePath])

  const symbolTypes = useMemo(() => {
    if (!analysis) return []
    const types = new Set(analysis.symbols.map((s: Symbol) => s.symbol_type))
    return Array.from(types).sort()
  }, [analysis])

  const summary = analysis?.summary

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
      {/* Header bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div className="flex items-center space-x-3.5">
          <div className="h-11 w-11 rounded-xl bg-gradient-to-tr from-cyan-500/20 to-indigo-500/20 text-cyan-400 border border-cyan-500/30 flex items-center justify-center shrink-0">
            <Code2 className="h-6 w-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h3 className="text-lg font-bold text-slate-100 tracking-tight">
                Code Intelligence & AST
              </h3>
              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-indigo-950 text-indigo-400 border border-indigo-800/60 uppercase">
                Phase 2
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Polyglot Tree-sitter & Python AST parser, deterministic symbol table, dependency graph & call graph.
            </p>
          </div>
        </div>

        <button
          onClick={handleRunAnalysis}
          disabled={analyzing}
          className="inline-flex items-center justify-center gap-2 px-4 py-2 text-xs font-semibold rounded-xl text-slate-950 bg-gradient-to-r from-cyan-400 to-indigo-400 hover:from-cyan-300 hover:to-indigo-300 transition shadow-lg shadow-cyan-500/20 disabled:opacity-60 cursor-pointer disabled:cursor-not-allowed shrink-0"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${analyzing ? 'animate-spin' : ''}`} />
          <span>{analyzing ? 'Analyzing Codebase...' : analysis ? 'Re-analyze ASTs' : 'Analyze Codebase'}</span>
        </button>
      </div>

      {error && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800/60 text-xs text-rose-300 flex items-start gap-3">
          <AlertTriangle className="h-4 w-4 shrink-0 text-rose-400 mt-0.5" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="py-12 text-center text-slate-400 text-sm animate-pulse">
          Checking repository code intelligence...
        </div>
      ) : !analysis ? (
        <div className="py-12 px-6 text-center rounded-xl bg-slate-950/50 border border-slate-800/80 space-y-4">
          <div className="h-12 w-12 mx-auto rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 flex items-center justify-center">
            <Terminal className="h-6 w-6" />
          </div>
          <div className="max-w-md mx-auto space-y-1.5">
            <h4 className="text-sm font-semibold text-slate-200">
              Code Intelligence Ready for {repositoryName}
            </h4>
            <p className="text-xs text-slate-400 leading-relaxed">
              Extract structural symbols, inspect local vs. external import relationships, verify circular dependencies, and map caller-to-callee call graphs across 10 languages.
            </p>
          </div>
          <button
            onClick={handleRunAnalysis}
            disabled={analyzing}
            className="inline-flex items-center gap-2 px-5 py-2.5 text-xs font-semibold rounded-xl text-slate-950 bg-cyan-400 hover:bg-cyan-300 transition shadow-lg shadow-cyan-500/20"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${analyzing ? 'animate-spin' : ''}`} />
            <span>Run AST Analysis</span>
          </button>
        </div>
      ) : (
        <div className="space-y-6">
          {/* Key Metric Cards */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
            <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-3">
              <span className="text-[11px] font-medium text-slate-400 block">Total Symbols</span>
              <span className="text-xl font-bold text-cyan-400 mt-0.5 block">
                {summary?.total_symbols.toLocaleString()}
              </span>
              <span className="text-[10px] text-slate-500">
                {summary?.total_functions} fn • {summary?.total_classes} class
              </span>
            </div>

            <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-3">
              <span className="text-[11px] font-medium text-slate-400 block">Imports</span>
              <span className="text-xl font-bold text-indigo-400 mt-0.5 block">
                {summary?.total_imports.toLocaleString()}
              </span>
              <span className="text-[10px] text-slate-500">Across repository</span>
            </div>

            <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-3">
              <span className="text-[11px] font-medium text-slate-400 block">Call Graph Edges</span>
              <span className="text-xl font-bold text-blue-400 mt-0.5 block">
                {summary?.total_call_edges.toLocaleString()}
              </span>
              <span className="text-[10px] text-slate-500">
                {summary?.resolved_call_edges} statically resolved
              </span>
            </div>

            <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-3">
              <span className="text-[11px] font-medium text-slate-400 block">Parsed Files</span>
              <span className="text-xl font-bold text-emerald-400 mt-0.5 block">
                {summary?.successfully_parsed_files} / {summary?.total_files_scanned}
              </span>
              <span className="text-[10px] text-slate-500">
                {summary?.unsupported_files} unsupported
              </span>
            </div>

            <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-3">
              <span className="text-[11px] font-medium text-slate-400 block">Circular Imports</span>
              <div className="flex items-center gap-1.5 mt-1">
                {summary?.has_circular_dependencies ? (
                  <>
                    <AlertTriangle className="h-4 w-4 text-amber-400 shrink-0" />
                    <span className="text-sm font-bold text-amber-400">
                      {summary.circular_dependency_cycles.length} Cycles
                    </span>
                  </>
                ) : (
                  <>
                    <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                    <span className="text-sm font-bold text-emerald-400">Clean</span>
                  </>
                )}
              </div>
              <span className="text-[10px] text-slate-500">Dependency health</span>
            </div>

            <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-3">
              <span className="text-[11px] font-medium text-slate-400 block">Languages</span>
              <span className="text-sm font-bold text-slate-200 mt-1 block truncate">
                {summary?.languages_analyzed.join(', ') || 'None'}
              </span>
              <span className="text-[10px] text-slate-500">Multi-AST parser</span>
            </div>
          </div>

          {/* Circular Dependencies Alert Banner */}
          {summary?.has_circular_dependencies && (
            <div className="p-4 rounded-xl bg-amber-950/40 border border-amber-800/60 space-y-2">
              <div className="flex items-center gap-2 text-amber-400 text-xs font-bold">
                <AlertTriangle className="h-4 w-4" />
                <span>Circular Dependency Warning Detected ({summary.circular_dependency_cycles.length} cycle{summary.circular_dependency_cycles.length > 1 ? 's' : ''})</span>
              </div>
              <div className="space-y-1">
                {summary.circular_dependency_cycles.map((cycle: string[], idx: number) => (
                  <div key={idx} className="text-xs font-mono text-slate-300 flex items-center gap-1.5 flex-wrap">
                    <span className="text-amber-400 font-semibold">Loop #{idx + 1}:</span>
                    {cycle.map((node: string, nIdx: number) => (
                      <React.Fragment key={nIdx}>
                        <span className="bg-slate-900/80 px-2 py-0.5 rounded border border-slate-800">{node}</span>
                        {nIdx < cycle.length - 1 && <ArrowRight className="h-3 w-3 text-amber-400/80" />}
                      </React.Fragment>
                    ))}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Navigation Tabs */}
          <div className="flex items-center space-x-1 border-b border-slate-800 pb-2 overflow-x-auto text-xs font-medium">
            <button
              onClick={() => setActiveTab('overview')}
              className={`px-3 py-1.5 rounded-lg transition ${
                activeTab === 'overview'
                  ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              Overview
            </button>
            <button
              onClick={() => setActiveTab('symbols')}
              className={`px-3 py-1.5 rounded-lg transition flex items-center gap-1.5 ${
                activeTab === 'symbols'
                  ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <Code2 className="h-3.5 w-3.5" />
              <span>Symbols ({analysis.symbols.length})</span>
            </button>
            <button
              onClick={() => setActiveTab('dependencies')}
              className={`px-3 py-1.5 rounded-lg transition flex items-center gap-1.5 ${
                activeTab === 'dependencies'
                  ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <Network className="h-3.5 w-3.5" />
              <span>Dependencies ({Object.keys(analysis.dependencies).length})</span>
            </button>
            <button
              onClick={() => setActiveTab('callgraph')}
              className={`px-3 py-1.5 rounded-lg transition flex items-center gap-1.5 ${
                activeTab === 'callgraph'
                  ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <GitFork className="h-3.5 w-3.5" />
              <span>Call Graph ({analysis.call_graph.length})</span>
            </button>
            <button
              onClick={() => setActiveTab('inspector')}
              className={`px-3 py-1.5 rounded-lg transition flex items-center gap-1.5 ${
                activeTab === 'inspector'
                  ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
              }`}
            >
              <FileText className="h-3.5 w-3.5" />
              <span>File AST Inspector</span>
            </button>
          </div>

          {/* TAB 1: OVERVIEW */}
          {activeTab === 'overview' && (
            <div className="space-y-6">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4 space-y-3">
                  <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                    <Layers className="h-4 w-4 text-cyan-400" />
                    <span>AST Extraction Statistics</span>
                  </h4>
                  <div className="space-y-2 text-xs">
                    <div className="flex justify-between py-1 border-b border-slate-800/60">
                      <span className="text-slate-400">Total Scanned Files</span>
                      <span className="font-mono text-slate-200">{summary?.total_files_scanned}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-slate-800/60">
                      <span className="text-slate-400">Successfully Parsed</span>
                      <span className="font-mono text-emerald-400">{summary?.successfully_parsed_files}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-slate-800/60">
                      <span className="text-slate-400">Syntax / Parse Errors</span>
                      <span className="font-mono text-amber-400">{summary?.failed_files}</span>
                    </div>
                    <div className="flex justify-between py-1 border-b border-slate-800/60">
                      <span className="text-slate-400">Unsupported Files</span>
                      <span className="font-mono text-slate-400">{summary?.unsupported_files}</span>
                    </div>
                    <div className="flex justify-between py-1">
                      <span className="text-slate-400">Last Analyzed</span>
                      <span className="font-mono text-slate-400 text-[10px]">
                        {summary ? new Date(summary.analyzed_at).toLocaleString() : 'N/A'}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-4 space-y-3">
                  <h4 className="text-xs font-semibold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                    <Box className="h-4 w-4 text-indigo-400" />
                    <span>Languages Evaluated</span>
                  </h4>
                  <div className="flex flex-wrap gap-2 pt-1">
                    {summary?.languages_analyzed.map((lang: string) => (
                      <span
                        key={lang}
                        className="px-2.5 py-1 rounded-lg text-xs font-medium bg-slate-900 border border-slate-700 text-slate-200"
                      >
                        {lang}
                      </span>
                    ))}
                  </div>
                  <p className="text-[11px] text-slate-400 leading-relaxed mt-2">
                    Python source is parsed via native Python <code className="text-cyan-400 font-mono">ast</code> for decorators, docstrings, and async/await signatures. Polyglot source files are parsed via official compiled Tree-sitter binary grammars.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: SYMBOLS EXPLORER */}
          {activeTab === 'symbols' && (
            <div className="space-y-4">
              {/* Search & Filter Bar */}
              <div className="flex flex-col sm:flex-row gap-3">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
                  <input
                    type="text"
                    value={symbolSearch}
                    onChange={(e) => setSymbolSearch(e.target.value)}
                    placeholder="Search symbols by name or file path..."
                    className="w-full pl-9 pr-4 py-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500/50"
                  />
                </div>
                <div className="flex items-center gap-1 overflow-x-auto pb-1 sm:pb-0">
                  <button
                    onClick={() => setSymbolTypeFilter('all')}
                    className={`px-2.5 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition ${
                      symbolTypeFilter === 'all'
                        ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
                        : 'bg-slate-950 text-slate-400 border border-slate-800 hover:text-slate-200'
                    }`}
                  >
                    All ({analysis.symbols.length})
                  </button>
                  {symbolTypes.map((type: string) => (
                    <button
                      key={type}
                      onClick={() => setSymbolTypeFilter(type)}
                      className={`px-2.5 py-1.5 rounded-lg text-xs font-medium capitalize whitespace-nowrap transition ${
                        symbolTypeFilter === type
                          ? 'bg-cyan-500/20 text-cyan-400 border border-cyan-500/30'
                          : 'bg-slate-950 text-slate-400 border border-slate-800 hover:text-slate-200'
                      }`}
                    >
                      {type}
                    </button>
                  ))}
                </div>
              </div>

              {/* Symbols Table */}
              <div className="overflow-x-auto rounded-xl border border-slate-800 max-h-[480px]">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950/80 text-slate-400 font-semibold border-b border-slate-800 sticky top-0 backdrop-blur">
                    <tr>
                      <th className="py-2.5 px-3">Symbol</th>
                      <th className="py-2.5 px-3">Type</th>
                      <th className="py-2.5 px-3">Location</th>
                      <th className="py-2.5 px-3">Parameters / Signature</th>
                      <th className="py-2.5 px-3">Visibility</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 bg-slate-900/40">
                    {filteredSymbols.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="py-8 text-center text-slate-500">
                          No symbols matching current filters.
                        </td>
                      </tr>
                    ) : (
                      filteredSymbols.map((sym: Symbol) => (
                        <tr key={sym.id} className="hover:bg-slate-800/30 transition">
                          <td className="py-2 px-3 font-mono font-medium text-slate-200">
                            <div className="flex items-center gap-1.5">
                              {sym.is_async && (
                                <span className="text-[10px] px-1 py-0.2 rounded bg-purple-950 text-purple-400 border border-purple-800/50">
                                  async
                                </span>
                              )}
                              <span>{sym.name}</span>
                            </div>
                            {sym.docstring && (
                              <p className="text-[10px] text-slate-400 font-sans truncate max-w-xs mt-0.5">
                                {sym.docstring}
                              </p>
                            )}
                          </td>
                          <td className="py-2 px-3">
                            <span className="px-2 py-0.5 rounded text-[10px] font-mono uppercase bg-slate-950 border border-slate-800 text-cyan-400">
                              {sym.symbol_type}
                            </span>
                          </td>
                          <td className="py-2 px-3 font-mono text-slate-400 text-[11px]">
                            {sym.file_path}:{sym.location.start_line}
                          </td>
                          <td className="py-2 px-3 font-mono text-slate-400 text-[11px]">
                            {sym.parameters && sym.parameters.length > 0
                              ? `(${sym.parameters.join(', ')})`
                              : sym.return_type
                              ? `-> ${sym.return_type}`
                              : '—'}
                          </td>
                          <td className="py-2 px-3">
                            <span
                              className={`text-[10px] font-medium ${
                                sym.visibility === 'public'
                                  ? 'text-emerald-400'
                                  : sym.visibility === 'private'
                                  ? 'text-amber-400'
                                  : 'text-slate-400'
                              }`}
                            >
                              {sym.visibility || 'public'}
                            </span>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 3: DEPENDENCIES EXPLORER */}
          {activeTab === 'dependencies' && (
            <div className="space-y-4">
              <div className="overflow-x-auto rounded-xl border border-slate-800 max-h-[480px]">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950/80 text-slate-400 font-semibold border-b border-slate-800 sticky top-0 backdrop-blur">
                    <tr>
                      <th className="py-2.5 px-3">File Path</th>
                      <th className="py-2.5 px-3">Depends On (Local)</th>
                      <th className="py-2.5 px-3">Imported By</th>
                      <th className="py-2.5 px-3">External Packages</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 bg-slate-900/40">
                    {Object.values(analysis.dependencies).map((dep) => (
                      <tr key={dep.file_path} className="hover:bg-slate-800/30 transition">
                        <td className="py-2.5 px-3 font-mono text-slate-200 font-medium whitespace-nowrap">
                          {dep.file_path}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-slate-300">
                          {dep.depends_on.length > 0 ? (
                            <div className="flex flex-wrap gap-1">
                              {dep.depends_on.map((d: string) => (
                                <span
                                  key={d}
                                  className="px-1.5 py-0.5 rounded text-[10px] bg-slate-950 border border-slate-800 text-indigo-300"
                                >
                                  {d}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span className="text-slate-500 text-[10px]">None</span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-slate-300">
                          {dep.imported_by.length > 0 ? (
                            <div className="flex flex-wrap gap-1">
                              {dep.imported_by.map((ib: string) => (
                                <span
                                  key={ib}
                                  className="px-1.5 py-0.5 rounded text-[10px] bg-slate-950 border border-slate-800 text-cyan-300"
                                >
                                  {ib}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span className="text-slate-500 text-[10px]">None</span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 font-mono text-slate-400">
                          {dep.external_dependencies.length > 0 ? (
                            <div className="flex flex-wrap gap-1">
                              {dep.external_dependencies.map((ext: string) => (
                                <span
                                  key={ext}
                                  className="px-1.5 py-0.5 rounded text-[10px] bg-slate-950 border border-slate-800 text-slate-400"
                                >
                                  {ext}
                                </span>
                              ))}
                            </div>
                          ) : (
                            <span className="text-slate-500 text-[10px]">None</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 4: CALL GRAPH */}
          {activeTab === 'callgraph' && (
            <div className="space-y-4">
              <div className="overflow-x-auto rounded-xl border border-slate-800 max-h-[480px]">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-950/80 text-slate-400 font-semibold border-b border-slate-800 sticky top-0 backdrop-blur">
                    <tr>
                      <th className="py-2.5 px-3">Caller Function</th>
                      <th className="py-2.5 px-3">Caller File & Line</th>
                      <th className="py-2.5 px-3">Callee Invocation</th>
                      <th className="py-2.5 px-3">Resolution Target</th>
                      <th className="py-2.5 px-3">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 bg-slate-900/40">
                    {analysis.call_graph.length === 0 ? (
                      <tr>
                        <td colSpan={5} className="py-8 text-center text-slate-500">
                          No function calls detected.
                        </td>
                      </tr>
                    ) : (
                      analysis.call_graph.map((edge) => (
                        <tr key={edge.id} className="hover:bg-slate-800/30 transition">
                          <td className="py-2 px-3 font-mono font-medium text-cyan-300">
                            {edge.caller_name}
                          </td>
                          <td className="py-2 px-3 font-mono text-slate-400 text-[11px]">
                            {edge.caller_file}:{edge.line_number}
                          </td>
                          <td className="py-2 px-3 font-mono font-semibold text-slate-200">
                            <div className="flex items-center gap-1">
                              <CornerDownRight className="h-3 w-3 text-slate-500" />
                              <span>{edge.callee_name}()</span>
                            </div>
                          </td>
                          <td className="py-2 px-3 font-mono text-[11px] text-slate-300">
                            {edge.resolved_callee_file ? (
                              <span className="text-indigo-300">
                                {edge.resolved_callee_file}
                              </span>
                            ) : (
                              <span className="text-slate-500">External / Stdlib</span>
                            )}
                          </td>
                          <td className="py-2 px-3">
                            {edge.is_resolved ? (
                              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-950 text-emerald-400 border border-emerald-800/50">
                                Resolved
                              </span>
                            ) : (
                              <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-950 text-slate-400 border border-slate-800">
                                External
                              </span>
                            )}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* TAB 5: FILE AST INSPECTOR */}
          {activeTab === 'inspector' && (
            <div className="space-y-4">
              <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 bg-slate-950/60 p-3 rounded-xl border border-slate-800">
                <span className="text-xs font-semibold text-slate-300">Select File:</span>
                <select
                  value={selectedFilePath}
                  onChange={(e) => setSelectedFilePath(e.target.value)}
                  className="bg-slate-900 border border-slate-700 text-xs text-slate-200 rounded-lg px-3 py-1.5 font-mono focus:outline-none focus:border-cyan-500 w-full sm:w-auto"
                >
                  {Object.keys(analysis.files).map((path: string) => (
                    <option key={path} value={path}>
                      {path}
                    </option>
                  ))}
                </select>
              </div>

              {selectedFileAnalysis && (
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  {/* File Metadata */}
                  <div className="md:col-span-1 bg-slate-950/50 border border-slate-800 rounded-xl p-4 space-y-3">
                    <h5 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                      File Overview
                    </h5>
                    <div className="space-y-1.5 text-xs">
                      <div className="flex justify-between">
                        <span className="text-slate-400">Language:</span>
                        <span className="font-semibold text-cyan-400">{selectedFileAnalysis.language}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">Status:</span>
                        <span
                          className={`font-semibold ${
                            selectedFileAnalysis.status === 'success' ? 'text-emerald-400' : 'text-amber-400'
                          }`}
                        >
                          {selectedFileAnalysis.status}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">Total Lines:</span>
                        <span className="font-mono text-slate-300">{selectedFileAnalysis.total_lines}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">Symbols Defined:</span>
                        <span className="font-mono text-slate-300">{selectedFileAnalysis.symbols.length}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">Imports Declared:</span>
                        <span className="font-mono text-slate-300">{selectedFileAnalysis.imports.length}</span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-slate-400">Function Calls:</span>
                        <span className="font-mono text-slate-300">{selectedFileAnalysis.function_calls.length}</span>
                      </div>
                    </div>
                  </div>

                  {/* Defined Symbols in this file */}
                  <div className="md:col-span-2 bg-slate-950/50 border border-slate-800 rounded-xl p-4 space-y-3">
                    <h5 className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                      Defined Symbols ({selectedFileAnalysis.symbols.length})
                    </h5>
                    {selectedFileAnalysis.symbols.length === 0 ? (
                      <p className="text-xs text-slate-500">No symbols declared in this file.</p>
                    ) : (
                      <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                        {selectedFileAnalysis.symbols.map((s: Symbol) => (
                          <div
                            key={s.id}
                            className="p-2 rounded bg-slate-900/80 border border-slate-800 text-xs font-mono flex items-center justify-between"
                          >
                            <span className="text-cyan-300 font-semibold">{s.name}</span>
                            <div className="flex items-center gap-2">
                              <span className="text-[10px] text-slate-400">line {s.location.start_line}</span>
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-950 text-indigo-400 uppercase">
                                {s.symbol_type}
                              </span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

