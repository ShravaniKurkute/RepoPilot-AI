import React, { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Bug,
  ShieldAlert,
  AlertTriangle,
  Info,
  CheckCircle2,
  RefreshCw,
  Sparkles,
  FileCode,
  ChevronRight,
  Filter,
  X,
  Clock,
  Layers,
} from 'lucide-react'
import type {
  CodeIssue,
  AnalysisRun,
  IssueSeverity,
  IssueStatus,
} from '../types'
import {
  runAiAnalysis,
  analyzeFile,
  getAnalysisStatus,
  getIssues,
  updateIssueStatus,
} from '../services/analysis'

interface CodeAnalysisSectionProps {
  repositoryId: string
  repositoryName: string
}

export const CodeAnalysisSection: React.FC<CodeAnalysisSectionProps> = ({
  repositoryId,
  repositoryName,
}) => {
  const [issues, setIssues] = useState<CodeIssue[]>([])
  const [selectedIssue, setSelectedIssue] = useState<CodeIssue | null>(null)
  const [currentRun, setCurrentRun] = useState<AnalysisRun | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [analyzing, setAnalyzing] = useState<boolean>(false)
  const [statusUpdating, setStatusUpdating] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0)

  // Filters
  const [selectedCategory, setSelectedCategory] = useState<string>('all')
  const [selectedSeverity, setSelectedSeverity] = useState<string>('all')
  const [selectedStatus, setSelectedStatus] = useState<string>('all')
  const [searchFilter, setSearchFilter] = useState<string>('')
  const [customFilePath, setCustomFilePath] = useState<string>('')
  const [showFileModal, setShowFileModal] = useState<boolean>(false)

  // Helper to extract run from API response
  const extractRun = useCallback((data: unknown): AnalysisRun | null => {
    if (!data || typeof data !== 'object') return null
    const obj = data as Record<string, unknown>
    if (obj.run && typeof obj.run === 'object') return obj.run as AnalysisRun
    if (obj.run_id && typeof obj.run_id === 'string') return obj as unknown as AnalysisRun
    return null
  }, [])

  // Poll analysis run status while analyzing is in progress
  useEffect(() => {
    let timer: ReturnType<typeof setInterval> | null = null
    let pollInterval: ReturnType<typeof setInterval> | null = null

    if (analyzing) {
      timer = setInterval(() => {
        setElapsedSeconds((prev) => prev + 1)
      }, 1000)

      pollInterval = setInterval(async () => {
        try {
          const statusRes = await getAnalysisStatus(repositoryId)
          const runObj = extractRun(statusRes.data)
          if (runObj) {
            setCurrentRun(runObj)
          }
        } catch {
          // ignore transient poll failure
        }
      }, 2000)
    }

    return () => {
      if (timer) clearInterval(timer)
      if (pollInterval) clearInterval(pollInterval)
    }
  }, [analyzing, repositoryId, extractRun])

  // Load issues and analysis run status when repository changes
  useEffect(() => {
    let ignore = false

    async function init() {
      try {
        const [issuesRes, statusRes] = await Promise.allSettled([
          getIssues(repositoryId),
          getAnalysisStatus(repositoryId),
        ])

        if (!ignore) {
          if (issuesRes.status === 'fulfilled') {
            const loadedIssues = issuesRes.value.data.issues || []
            setIssues(loadedIssues)
            setSelectedIssue(loadedIssues.length > 0 ? loadedIssues[0] : null)
          }
          if (statusRes.status === 'fulfilled') {
            const runObj = extractRun(statusRes.value.data)
            if (runObj) setCurrentRun(runObj)
          }
          setError(null)
          setLoading(false)
        }
      } catch (err: unknown) {
        if (!ignore) {
          const msg = err instanceof Error ? err.message : 'Failed to load analysis findings'
          setError(msg)
          setLoading(false)
        }
      }
    }

    init()

    return () => {
      ignore = true
    }
  }, [repositoryId, extractRun])

  // Reload data on user actions
  const reloadData = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [issuesRes, statusRes] = await Promise.allSettled([
        getIssues(repositoryId),
        getAnalysisStatus(repositoryId),
      ])

      if (issuesRes.status === 'fulfilled') {
        const loadedIssues = issuesRes.value.data.issues || []
        setIssues(loadedIssues)
        if (loadedIssues.length > 0) {
          setSelectedIssue(loadedIssues[0])
        }
      }
      if (statusRes.status === 'fulfilled') {
        const runObj = extractRun(statusRes.value.data)
        if (runObj) setCurrentRun(runObj)
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load analysis findings'
      setError(msg)
    } finally {
      setLoading(false)
    }
  }, [repositoryId, extractRun])

  // Trigger full repository AI analysis
  const handleFullAnalysis = async () => {
    setAnalyzing(true)
    setElapsedSeconds(0)
    setError(null)
    try {
      const res = await runAiAnalysis(repositoryId)
      const runObj = extractRun(res.data)
      if (runObj) {
        setCurrentRun(runObj)
      }
      // Refresh issues list
      const issuesRes = await getIssues(repositoryId)
      const loaded = issuesRes.data.issues || []
      setIssues(loaded)
      if (loaded.length > 0) {
        setSelectedIssue(loaded[0])
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'AI code analysis failed'
      setError(msg)
      try {
        const statusRes = await getAnalysisStatus(repositoryId)
        const runObj = extractRun(statusRes.data)
        if (runObj) setCurrentRun(runObj)
      } catch {
        // ignore
      }
    } finally {
      setAnalyzing(false)
    }
  }

  // Trigger single file AI analysis
  const handleAnalyzeFile = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!customFilePath.trim()) return

    setAnalyzing(true)
    setElapsedSeconds(0)
    setError(null)
    try {
      const res = await analyzeFile(repositoryId, {
        file_path: customFilePath.trim(),
      })
      const runObj = extractRun(res.data)
      if (runObj) {
        setCurrentRun(runObj)
      }
      setShowFileModal(false)
      setCustomFilePath('')
      const issuesRes = await getIssues(repositoryId)
      const loaded = issuesRes.data.issues || []
      setIssues(loaded)
      if (loaded.length > 0) {
        setSelectedIssue(loaded[0])
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'File analysis failed'
      setError(msg)
      try {
        const statusRes = await getAnalysisStatus(repositoryId)
        const runObj = extractRun(statusRes.data)
        if (runObj) setCurrentRun(runObj)
      } catch {
        // ignore
      }
    } finally {
      setAnalyzing(false)
    }
  }

  // Update status of an individual issue
  const handleStatusChange = async (issueId: string, newStatus: IssueStatus) => {
    setStatusUpdating(true)
    try {
      const res = await updateIssueStatus(issueId, newStatus)
      const updatedIssue = res.data
      setIssues((prev) =>
        prev.map((item) => (item.issue_id === issueId ? updatedIssue : item))
      )
      if (selectedIssue?.issue_id === issueId) {
        setSelectedIssue(updatedIssue)
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to update issue status'
      setError(msg)
    } finally {
      setStatusUpdating(false)
    }
  }

  // Filtered issues computation
  const filteredIssues = useMemo(() => {
    return issues.filter((issue) => {
      if (selectedCategory !== 'all' && issue.category !== selectedCategory) return false
      if (selectedSeverity !== 'all' && issue.severity !== selectedSeverity) return false
      if (selectedStatus !== 'all' && issue.status !== selectedStatus) return false
      if (searchFilter.trim()) {
        const query = searchFilter.toLowerCase()
        const matchesTitle = issue.issue_title.toLowerCase().includes(query)
        const matchesFile = issue.file_path.toLowerCase().includes(query)
        const matchesSymbol = (issue.affected_symbol || '').toLowerCase().includes(query)
        const matchesCwe = (issue.cwe_id || '').toLowerCase().includes(query)
        if (!matchesTitle && !matchesFile && !matchesSymbol && !matchesCwe) return false
      }
      return true
    })
  }, [issues, selectedCategory, selectedSeverity, selectedStatus, searchFilter])

  // Count severities
  const severityCounts = useMemo(() => {
    const counts: Record<IssueSeverity, number> = {
      Critical: 0,
      High: 0,
      Medium: 0,
      Low: 0,
      Informational: 0,
    }
    issues.forEach((issue) => {
      if (counts[issue.severity] !== undefined) {
        counts[issue.severity]++
      }
    })
    return counts
  }, [issues])

  // Category counts
  const categoryCounts = useMemo(() => {
    const counts = { logic_bug: 0, security_vulnerability: 0, code_smell: 0 }
    issues.forEach((issue) => {
      if (counts[issue.category] !== undefined) {
        counts[issue.category]++
      }
    })
    return counts
  }, [issues])

  const getSeverityBadgeClass = (severity: IssueSeverity) => {
    switch (severity) {
      case 'Critical':
        return 'bg-rose-500/10 text-rose-400 border-rose-500/20'
      case 'High':
        return 'bg-amber-500/10 text-amber-400 border-amber-500/20'
      case 'Medium':
        return 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20'
      case 'Low':
        return 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20'
      case 'Informational':
      default:
        return 'bg-slate-500/10 text-slate-400 border-slate-500/20'
    }
  }

  const getStatusBadgeClass = (status: IssueStatus) => {
    switch (status) {
      case 'Open':
        return 'bg-rose-500/15 text-rose-300 border-rose-500/30'
      case 'Confirmed':
        return 'bg-amber-500/15 text-amber-300 border-amber-500/30'
      case 'Resolved':
        return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
      case 'False Positive':
      case 'Ignored':
      default:
        return 'bg-slate-500/15 text-slate-400 border-slate-500/30'
    }
  }

  const getRunStatusBadgeClass = (status: string) => {
    switch (status) {
      case 'completed':
        return 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
      case 'timed_out':
        return 'bg-amber-500/20 text-amber-300 border-amber-500/40'
      case 'failed':
        return 'bg-rose-500/20 text-rose-300 border-rose-500/40'
      case 'running':
        return 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40 animate-pulse'
      default:
        return 'bg-slate-700 text-slate-300 border-slate-600'
    }
  }

  const isTimeout = useMemo(() => {
    if (currentRun?.status === 'timed_out') return true
    if (!error) return false
    const lower = error.toLowerCase()
    return lower.includes('timed out') || lower.includes('timeout')
  }, [currentRun?.status, error])

  const isGeminiApiError = useMemo(() => {
    if (!error || isTimeout) return false
    const lower = error.toLowerCase()
    return (
      lower.includes('401') ||
      lower.includes('404') ||
      lower.includes('503') ||
      lower.includes('429') ||
      lower.includes('high demand') ||
      lower.includes('gemini api') ||
      lower.includes('api_key')
    )
  }, [error, isTimeout])

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6">
      {/* Header & Main Actions */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-800 pb-5">
        <div>
          <div className="flex items-center space-x-2">
            <span className="p-2 rounded-lg bg-rose-500/10 text-rose-400">
              <Bug className="h-5 w-5" />
            </span>
            <h2 className="text-xl font-bold text-slate-100">
              AI Code Analysis & Bug Detection
            </h2>
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
              Phase 4
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-1">
            AST-guided & RAG-contextualized Gemini reasoning for logic bugs, OWASP vulnerabilities, and code smells in{' '}
            <span className="text-cyan-300 font-medium">{repositoryName}</span>
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <button
            type="button"
            onClick={() => setShowFileModal(true)}
            className="flex items-center space-x-1.5 px-3 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium rounded-lg border border-slate-700 transition"
          >
            <FileCode className="h-3.5 w-3.5 text-slate-400" />
            <span>Scan File</span>
          </button>

          <button
            type="button"
            onClick={handleFullAnalysis}
            disabled={analyzing}
            className="flex items-center space-x-2 px-4 py-2 bg-gradient-to-r from-rose-500 to-amber-500 hover:from-rose-600 hover:to-amber-600 disabled:opacity-50 text-white text-xs font-semibold rounded-lg shadow-md hover:shadow-rose-500/10 transition"
          >
            {analyzing ? (
              <>
                <RefreshCw className="h-4 w-4 animate-spin" />
                <span>Analyzing Repository...</span>
              </>
            ) : (
              <>
                <Sparkles className="h-4 w-4" />
                <span>Run AI Bug Scan</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Active Analysis Progress Feedback Banner */}
      {analyzing && (
        <div className="p-4 bg-cyan-950/40 border border-cyan-700/60 rounded-xl space-y-3 shadow-lg">
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center space-x-2.5 text-cyan-300 font-semibold">
              <RefreshCw className="h-4 w-4 animate-spin text-cyan-400" />
              <span>
                {currentRun?.current_stage ? (
                  <>
                    <span className="px-2 py-0.5 mr-2 rounded-full text-[10px] uppercase font-bold tracking-wider bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">
                      Stage: {currentRun.current_stage}
                    </span>
                    {currentRun.stage_message || 'Processing repository analysis...'}
                  </>
                ) : (
                  'Analyzing Repository with Gemini 3.8 Flash (Reasoning Active)...'
                )}
              </span>
            </div>
            <div className="flex items-center space-x-2 text-slate-400">
              <Clock className="h-3.5 w-3.5 text-cyan-400" />
              <span>Elapsed: <strong className="text-cyan-300 font-mono">{elapsedSeconds}s</strong></span>
            </div>
          </div>

          <div className="space-y-1.5">
            <div className="flex justify-between text-[11px] text-slate-300">
              <span>
                {currentRun?.current_stage === 'Running AI Analysis' ? (
                  <>
                    Processed:{' '}
                    <strong className="text-cyan-400 font-semibold">
                      {currentRun?.analyzed_files ?? 0}
                    </strong>{' '}
                    of {currentRun?.total_files ?? '...'} files
                  </>
                ) : (
                  <span>Stage: <strong className="text-cyan-300">{currentRun?.current_stage ?? 'Initializing'}</strong></span>
                )}
              </span>
              <span>
                {currentRun?.current_stage === 'Running AI Analysis' && currentRun?.total_files && currentRun.total_files > 0
                  ? `${Math.round(((currentRun.analyzed_files || 0) / currentRun.total_files) * 100)}%`
                  : currentRun?.stage_message || 'Synthesizing context...'}
              </span>
            </div>
            <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-gradient-to-r from-cyan-500 to-amber-500 h-1.5 rounded-full transition-all duration-500"
                style={{
                  width: `${
                    currentRun?.current_stage === 'Running AI Analysis' && currentRun?.total_files && currentRun.total_files > 0
                      ? Math.min(100, Math.max(10, Math.round(((currentRun.analyzed_files || 0) / currentRun.total_files) * 100)))
                      : currentRun?.current_stage === 'Generating Embeddings'
                      ? 50
                      : currentRun?.current_stage === 'Building Vector Index'
                      ? 70
                      : currentRun?.current_stage === 'Extracting Source Code' || currentRun?.current_stage === 'Generating Code Chunks'
                      ? 35
                      : 20
                  }%`,
                }}
              />
            </div>
          </div>
          <p className="text-[11px] text-slate-400 italic">
            Repository-aware RAG contextualization and deep reasoning models active. Timeout configured for 180s.
          </p>
        </div>
      )}

      {/* Analysis Timed Out Banner */}
      {isTimeout && !analyzing && (
        <div className="p-4 bg-amber-950/40 border border-amber-600/50 rounded-xl space-y-2 text-xs text-amber-200">
          <div className="flex items-start justify-between">
            <div className="flex items-center space-x-2 font-bold text-amber-300 text-sm">
              <Clock className="h-4 w-4 text-amber-400" />
              <span>Analysis Request Timed Out</span>
            </div>
            <button
              type="button"
              onClick={() => setError(null)}
              className="text-amber-400 hover:text-amber-200"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <p className="text-slate-300 leading-relaxed">
            The Gemini code analysis request timed out. This occurs when analyzing large codebases or complex file slices requiring extended reasoning time beyond 180s. Partial findings have been preserved.
          </p>
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <button
              type="button"
              onClick={handleFullAnalysis}
              className="px-3 py-1.5 bg-amber-600/30 hover:bg-amber-600/40 border border-amber-500/50 rounded-lg text-amber-200 font-medium transition"
            >
              Retry Full Scan
            </button>
            <button
              type="button"
              onClick={() => setShowFileModal(true)}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 border border-slate-700 rounded-lg text-slate-200 font-medium transition"
            >
              Scan Individual File
            </button>
            <span className="text-[11px] text-slate-400">
              Tip: You can increase <code className="text-cyan-400 font-mono">GEMINI_REQUEST_TIMEOUT</code> in <code className="text-cyan-400 font-mono">backend/.env</code>.
            </span>
          </div>
        </div>
      )}

      {/* Gemini API Error Banner */}
      {isGeminiApiError && !analyzing && (
        <div className="p-4 bg-rose-950/40 border border-rose-700/60 rounded-xl space-y-2 text-xs text-rose-200">
          <div className="flex items-start justify-between">
            <div className="flex items-center space-x-2 font-bold text-rose-300 text-sm">
              <ShieldAlert className="h-4 w-4 text-rose-400" />
              <span>Google Gemini API Notice</span>
            </div>
            <button
              type="button"
              onClick={() => setError(null)}
              className="text-rose-400 hover:text-rose-200"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <p className="text-slate-300 leading-relaxed">{error}</p>
          {error && (error.includes('503') || error.toLowerCase().includes('high demand')) ? (
            <p className="text-[11px] text-amber-300">
              Google Gemini is currently experiencing temporary high demand spikes. Please wait a moment and retry.
            </p>
          ) : error && error.includes('401') ? (
            <p className="text-[11px] text-amber-300">
              Please check that your GEMINI_API_KEY is properly configured in <code className="font-mono">backend/.env</code>.
            </p>
          ) : null}
          <div className="pt-1">
            <button
              type="button"
              onClick={handleFullAnalysis}
              className="px-3 py-1.5 bg-rose-600/30 hover:bg-rose-600/40 border border-rose-500/50 rounded-lg text-rose-200 font-medium transition"
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {/* Generic Notice */}
      {error && !isTimeout && !isGeminiApiError && (
        <div className="flex items-start space-x-3 p-3.5 bg-rose-950/40 border border-rose-800/60 rounded-xl text-rose-300 text-xs">
          <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5 text-rose-400" />
          <div className="flex-1">
            <span className="font-semibold">Analysis Notice: </span>
            <span>{error}</span>
          </div>
          <button
            type="button"
            onClick={() => setError(null)}
            className="text-rose-400 hover:text-rose-200"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      )}

      {/* Severity Metrics Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <button
          type="button"
          onClick={() => setSelectedSeverity('all')}
          className={`p-3 rounded-xl border text-left transition ${
            selectedSeverity === 'all'
              ? 'bg-slate-800 border-cyan-500/50 shadow-sm'
              : 'bg-slate-900/60 border-slate-800 hover:bg-slate-800/50'
          }`}
        >
          <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">Total Issues</div>
          <div className="text-xl font-bold text-slate-100 mt-1">{issues.length}</div>
        </button>

        <button
          type="button"
          onClick={() => setSelectedSeverity(selectedSeverity === 'Critical' ? 'all' : 'Critical')}
          className={`p-3 rounded-xl border text-left transition ${
            selectedSeverity === 'Critical'
              ? 'bg-rose-950/40 border-rose-500 shadow-sm'
              : 'bg-slate-900/60 border-slate-800 hover:bg-slate-800/50'
          }`}
        >
          <div className="text-[11px] font-medium text-rose-400 uppercase tracking-wider flex items-center justify-between">
            <span>Critical</span>
            <span className="h-2 w-2 rounded-full bg-rose-500" />
          </div>
          <div className="text-xl font-bold text-rose-400 mt-1">{severityCounts.Critical}</div>
        </button>

        <button
          type="button"
          onClick={() => setSelectedSeverity(selectedSeverity === 'High' ? 'all' : 'High')}
          className={`p-3 rounded-xl border text-left transition ${
            selectedSeverity === 'High'
              ? 'bg-amber-950/40 border-amber-500 shadow-sm'
              : 'bg-slate-900/60 border-slate-800 hover:bg-slate-800/50'
          }`}
        >
          <div className="text-[11px] font-medium text-amber-400 uppercase tracking-wider flex items-center justify-between">
            <span>High</span>
            <span className="h-2 w-2 rounded-full bg-amber-500" />
          </div>
          <div className="text-xl font-bold text-amber-400 mt-1">{severityCounts.High}</div>
        </button>

        <button
          type="button"
          onClick={() => setSelectedSeverity(selectedSeverity === 'Medium' ? 'all' : 'Medium')}
          className={`p-3 rounded-xl border text-left transition ${
            selectedSeverity === 'Medium'
              ? 'bg-yellow-950/40 border-yellow-500 shadow-sm'
              : 'bg-slate-900/60 border-slate-800 hover:bg-slate-800/50'
          }`}
        >
          <div className="text-[11px] font-medium text-yellow-400 uppercase tracking-wider flex items-center justify-between">
            <span>Medium</span>
            <span className="h-2 w-2 rounded-full bg-yellow-400" />
          </div>
          <div className="text-xl font-bold text-yellow-400 mt-1">{severityCounts.Medium}</div>
        </button>

        <button
          type="button"
          onClick={() => setSelectedSeverity(selectedSeverity === 'Low' ? 'all' : 'Low')}
          className={`p-3 rounded-xl border text-left transition ${
            selectedSeverity === 'Low'
              ? 'bg-cyan-950/40 border-cyan-500 shadow-sm'
              : 'bg-slate-900/60 border-slate-800 hover:bg-slate-800/50'
          }`}
        >
          <div className="text-[11px] font-medium text-cyan-400 uppercase tracking-wider flex items-center justify-between">
            <span>Low</span>
            <span className="h-2 w-2 rounded-full bg-cyan-400" />
          </div>
          <div className="text-xl font-bold text-cyan-400 mt-1">{severityCounts.Low}</div>
        </button>

        <button
          type="button"
          onClick={() => setSelectedSeverity(selectedSeverity === 'Informational' ? 'all' : 'Informational')}
          className={`p-3 rounded-xl border text-left transition ${
            selectedSeverity === 'Informational'
              ? 'bg-slate-800 border-slate-500 shadow-sm'
              : 'bg-slate-900/60 border-slate-800 hover:bg-slate-800/50'
          }`}
        >
          <div className="text-[11px] font-medium text-slate-400 uppercase tracking-wider flex items-center justify-between">
            <span>Info</span>
            <span className="h-2 w-2 rounded-full bg-slate-400" />
          </div>
          <div className="text-xl font-bold text-slate-300 mt-1">{severityCounts.Informational}</div>
        </button>
      </div>

      {/* Analysis Run Status Banner */}
      {currentRun && (
        <div className="p-3 bg-slate-800/50 border border-slate-700/60 rounded-xl flex flex-wrap items-center justify-between gap-3 text-xs text-slate-300">
          <div className="flex items-center space-x-2">
            <Clock className="h-4 w-4 text-cyan-400" />
            <span>
              Last Analysis Run:{' '}
              <span className="text-slate-100 font-semibold">{currentRun.target_type}</span>
              {currentRun.target_path ? ` (${currentRun.target_path})` : ''}
            </span>
            <span
              className={`px-2 py-0.5 rounded-full text-[10px] uppercase font-bold border ${getRunStatusBadgeClass(
                currentRun.status
              )}`}
            >
              {currentRun.status}
            </span>
            {currentRun.current_stage && (
              <span className="px-2 py-0.5 rounded-full text-[10px] bg-slate-700/60 text-slate-300 border border-slate-600/50">
                {currentRun.current_stage}
              </span>
            )}
          </div>

          <div className="flex items-center space-x-4">
            <span>
              Analyzed Files:{' '}
              <strong className="text-cyan-300 font-semibold">
                {currentRun.analyzed_files} / {currentRun.total_files}
              </strong>
            </span>
            <span>
              Detected Issues:{' '}
              <strong className="text-rose-400 font-semibold">{currentRun.total_issues}</strong>
            </span>
            <button
              type="button"
              onClick={reloadData}
              className="text-slate-400 hover:text-slate-200"
              title="Refresh findings"
            >
              <RefreshCw className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      )}

      {/* Category Tabs & Filter Bar */}
      <div className="space-y-3">
        {/* Category Tabs */}
        <div className="flex flex-wrap items-center gap-2 border-b border-slate-800 pb-3">
          <button
            type="button"
            onClick={() => setSelectedCategory('all')}
            className={`px-3 py-1.5 rounded-lg text-xs font-medium transition ${
              selectedCategory === 'all'
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            All Categories ({issues.length})
          </button>
          <button
            type="button"
            onClick={() => setSelectedCategory('logic_bug')}
            className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition ${
              selectedCategory === 'logic_bug'
                ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <Bug className="h-3.5 w-3.5 text-rose-400" />
            <span>Logic Bugs ({categoryCounts.logic_bug})</span>
          </button>
          <button
            type="button"
            onClick={() => setSelectedCategory('security_vulnerability')}
            className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition ${
              selectedCategory === 'security_vulnerability'
                ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <ShieldAlert className="h-3.5 w-3.5 text-amber-400" />
            <span>Security Vulnerabilities ({categoryCounts.security_vulnerability})</span>
          </button>
          <button
            type="button"
            onClick={() => setSelectedCategory('code_smell')}
            className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition ${
              selectedCategory === 'code_smell'
                ? 'bg-yellow-500/20 text-yellow-300 border border-yellow-500/30'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
            }`}
          >
            <Layers className="h-3.5 w-3.5 text-yellow-400" />
            <span>Code Smells ({categoryCounts.code_smell})</span>
          </button>
        </div>

        {/* Filter Bar */}
        <div className="flex flex-col sm:flex-row items-center gap-3">
          <div className="relative flex-1 w-full">
            <Filter className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
            <input
              type="text"
              placeholder="Search by title, file path, symbol, or CWE ID..."
              value={searchFilter}
              onChange={(e) => setSearchFilter(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 bg-slate-950/70 border border-slate-800 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
            />
          </div>

          <div className="flex items-center space-x-2 w-full sm:w-auto">
            <select
              value={selectedStatus}
              onChange={(e) => setSelectedStatus(e.target.value)}
              className="bg-slate-950/70 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-cyan-500"
            >
              <option value="all">All Statuses</option>
              <option value="Open">Open</option>
              <option value="Confirmed">Confirmed</option>
              <option value="False Positive">False Positive</option>
              <option value="Resolved">Resolved</option>
              <option value="Ignored">Ignored</option>
            </select>

            <select
              value={selectedSeverity}
              onChange={(e) => setSelectedSeverity(e.target.value)}
              className="bg-slate-950/70 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:border-cyan-500"
            >
              <option value="all">All Severities</option>
              <option value="Critical">Critical</option>
              <option value="High">High</option>
              <option value="Medium">Medium</option>
              <option value="Low">Low</option>
              <option value="Informational">Informational</option>
            </select>
          </div>
        </div>
      </div>

      {/* Main Content: Split Issue List + Detail Pane */}
      {loading ? (
        <div className="p-12 text-center text-slate-500 text-xs">
          <RefreshCw className="h-6 w-6 animate-spin mx-auto text-slate-600 mb-2" />
          <span>Loading repository issues...</span>
        </div>
      ) : filteredIssues.length === 0 ? (
        <div className="p-12 text-center border border-dashed border-slate-800 rounded-xl text-slate-500">
          <Bug className="h-8 w-8 mx-auto text-slate-600 mb-2" />
          <p className="text-sm font-medium text-slate-400">No issues found</p>
          <p className="text-xs text-slate-500 mt-1">
            {issues.length === 0
              ? 'Click "Run AI Bug Scan" to analyze the repository for potential vulnerabilities and bugs.'
              : 'No issues match the selected filters.'}
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Left Column: Issue List */}
          <div className="lg:col-span-5 space-y-2 max-h-[640px] overflow-y-auto pr-1">
            {filteredIssues.map((issue) => {
              const isSelected = selectedIssue?.issue_id === issue.issue_id
              return (
                <div
                  key={issue.issue_id}
                  onClick={() => setSelectedIssue(issue)}
                  className={`p-3 rounded-xl border text-left cursor-pointer transition ${
                    isSelected
                      ? 'bg-slate-800/90 border-cyan-500/70 shadow-md ring-1 ring-cyan-500/40'
                      : 'bg-slate-900/60 border-slate-800/80 hover:bg-slate-800/40 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <div className="flex items-center space-x-1.5 flex-wrap gap-y-1">
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${getSeverityBadgeClass(
                          issue.severity
                        )}`}
                      >
                        {issue.severity}
                      </span>
                      {issue.cwe_id && (
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 border border-slate-700">
                          {issue.cwe_id}
                        </span>
                      )}
                      <span
                        className={`text-[10px] font-medium px-1.5 py-0.5 rounded border ${getStatusBadgeClass(
                          issue.status
                        )}`}
                      >
                        {issue.status}
                      </span>
                    </div>

                    <span className="text-[10px] text-slate-400 font-mono">
                      {Math.round(issue.confidence_score * 100)}% conf
                    </span>
                  </div>

                  <h3 className="text-xs font-semibold text-slate-200 line-clamp-1">
                    {issue.issue_title}
                  </h3>

                  <div className="flex items-center justify-between text-[11px] text-slate-400 mt-2 font-mono">
                    <span className="truncate max-w-[200px]" title={issue.file_path}>
                      {issue.file_path}:{issue.start_line}
                    </span>
                    <span className="text-cyan-400 flex items-center space-x-1 shrink-0">
                      <span>Inspect</span>
                      <ChevronRight className="h-3 w-3" />
                    </span>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Right Column: Detailed Issue Inspector */}
          <div className="lg:col-span-7 bg-slate-950/80 border border-slate-800 rounded-xl p-5 space-y-5 max-h-[640px] overflow-y-auto">
            {selectedIssue ? (
              <>
                {/* Header with Title & Triage Status Dropdown */}
                <div className="border-b border-slate-800/80 pb-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center space-x-2">
                      <span
                        className={`text-xs font-bold px-2.5 py-1 rounded-full border ${getSeverityBadgeClass(
                          selectedIssue.severity
                        )}`}
                      >
                        {selectedIssue.severity} Severity
                      </span>
                      <span className="text-xs px-2.5 py-1 rounded-full bg-slate-800 text-slate-300 border border-slate-700 capitalize">
                        {selectedIssue.category.replace('_', ' ')}
                      </span>
                      {selectedIssue.cwe_id && (
                        <span className="text-xs font-mono px-2 py-1 rounded bg-slate-800/80 text-amber-300 border border-amber-500/30">
                          {selectedIssue.cwe_id}
                        </span>
                      )}
                    </div>

                    {/* Status Mutator */}
                    <div className="flex items-center space-x-2">
                      <span className="text-xs text-slate-400">Status:</span>
                      <select
                        value={selectedIssue.status}
                        disabled={statusUpdating}
                        onChange={(e) =>
                          handleStatusChange(
                            selectedIssue.issue_id,
                            e.target.value as IssueStatus
                          )
                        }
                        className="bg-slate-900 border border-slate-700 rounded-lg px-2.5 py-1 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
                      >
                        <option value="Open">Open</option>
                        <option value="Confirmed">Confirmed</option>
                        <option value="False Positive">False Positive</option>
                        <option value="Resolved">Resolved</option>
                        <option value="Ignored">Ignored</option>
                      </select>
                    </div>
                  </div>

                  <h2 className="text-base font-bold text-slate-100 mt-3">
                    {selectedIssue.issue_title}
                  </h2>

                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400 mt-1 font-mono">
                    <span>
                      File: <strong className="text-cyan-300">{selectedIssue.file_path}</strong> (Lines {selectedIssue.start_line}-{selectedIssue.end_line})
                    </span>
                    {selectedIssue.affected_symbol && (
                      <span>
                        Symbol: <strong className="text-purple-300">{selectedIssue.affected_symbol}</strong>
                      </span>
                    )}
                    <span>
                      Language: <strong className="text-slate-200">{selectedIssue.language}</strong>
                    </span>
                  </div>
                </div>

                {/* Evidence Code Snippet */}
                <div>
                  <div className="flex items-center justify-between text-xs font-semibold text-slate-300 mb-1.5">
                    <span>Verbatim Evidence</span>
                    <span className="text-[10px] text-slate-500 font-mono">Lines {selectedIssue.start_line}-{selectedIssue.end_line}</span>
                  </div>
                  <pre className="p-3 bg-slate-900 border border-slate-800 rounded-lg text-xs font-mono text-rose-300/90 overflow-x-auto whitespace-pre-wrap leading-relaxed">
                    {selectedIssue.evidence}
                  </pre>
                </div>

                {/* Technical Explanation */}
                <div>
                  <h3 className="text-xs font-semibold text-slate-300 mb-1">
                    Technical Explanation
                  </h3>
                  <p className="text-xs text-slate-400 leading-relaxed bg-slate-900/40 p-3 rounded-lg border border-slate-800/60">
                    {selectedIssue.technical_explanation}
                  </p>
                </div>

                {/* Potential Impact */}
                <div>
                  <h3 className="text-xs font-semibold text-amber-300 mb-1 flex items-center space-x-1.5">
                    <ShieldAlert className="h-3.5 w-3.5" />
                    <span>Potential Impact</span>
                  </h3>
                  <p className="text-xs text-slate-400 leading-relaxed bg-amber-950/20 p-3 rounded-lg border border-amber-900/30">
                    {selectedIssue.potential_impact}
                  </p>
                </div>

                {/* Suggested Fix */}
                <div>
                  <h3 className="text-xs font-semibold text-emerald-300 mb-1 flex items-center space-x-1.5">
                    <CheckCircle2 className="h-3.5 w-3.5" />
                    <span>Remediation Guidance</span>
                  </h3>
                  <div className="p-3 bg-emerald-950/20 border border-emerald-900/30 rounded-lg text-xs text-slate-300 whitespace-pre-wrap font-mono leading-relaxed">
                    {selectedIssue.suggested_fix}
                  </div>
                </div>

                {/* Metadata & Related Files Footer */}
                <div className="border-t border-slate-800/80 pt-3 flex flex-wrap items-center justify-between text-[11px] text-slate-500 font-mono">
                  <span>Confidence: {Math.round(selectedIssue.confidence_score * 100)}%</span>
                  <span>Detection: {selectedIssue.detection_method}</span>
                  {selectedIssue.related_files && selectedIssue.related_files.length > 0 && (
                    <span>Related: {selectedIssue.related_files.join(', ')}</span>
                  )}
                </div>
              </>
            ) : (
              <div className="p-12 text-center text-slate-500 text-xs">
                <Info className="h-6 w-6 mx-auto text-slate-600 mb-2" />
                <span>Select an issue from the list to view comprehensive diagnostic details.</span>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Single File Scan Modal */}
      {showFileModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 max-w-md w-full shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-slate-100 flex items-center space-x-2">
                <FileCode className="h-4 w-4 text-cyan-400" />
                <span>Scan Specific File</span>
              </h3>
              <button
                type="button"
                onClick={() => setShowFileModal(false)}
                className="text-slate-400 hover:text-slate-200"
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <p className="text-xs text-slate-400">
              Enter the repository relative path to target AI code analysis on a single file:
            </p>

            <form onSubmit={handleAnalyzeFile} className="space-y-4">
              <input
                type="text"
                placeholder="e.g. app/core/security.py or src/utils.ts"
                value={customFilePath}
                onChange={(e) => setCustomFilePath(e.target.value)}
                className="w-full px-3 py-2 bg-slate-950 border border-slate-800 rounded-lg text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
                required
              />

              <div className="flex items-center justify-end space-x-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowFileModal(false)}
                  className="px-3 py-1.5 text-xs text-slate-400 hover:text-slate-200"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={analyzing || !customFilePath.trim()}
                  className="px-4 py-1.5 bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white text-xs font-medium rounded-lg"
                >
                  {analyzing ? 'Scanning...' : 'Start Scan'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
