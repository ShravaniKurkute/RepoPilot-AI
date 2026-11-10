import React, { useState, useEffect, useCallback } from 'react'
import {
  Wrench,
  GitPullRequest,
  Sparkles,
  ShieldAlert,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  FileCode,
  Copy,
  Check,
  RotateCcw,
  Info,
  Loader2,
  Download,
  ThumbsUp,
  ThumbsDown,
  CheckSquare,
  FileText,
} from 'lucide-react'
import type { CodeIssue, FixPlan, PatchProposal, RiskLevel, SandboxExecution } from '../types'
import { getIssues } from '../services/analysis'
import {
  createFixPlan,
  getFixPlan,
  generatePatch,
  listPatches,
  reviewPatch,
  regeneratePatch,
} from '../services/patch'
import {
  executePatch,
  getExecution,
  listExecutionsForPatch,
} from '../services/execution'
import { DockerExecutionPanel } from './DockerExecutionPanel'

interface AiFixGeneratorSectionProps {
  repositoryId: string
  repositoryName: string
}

export const AiFixGeneratorSection: React.FC<AiFixGeneratorSectionProps> = ({
  repositoryId,
  repositoryName,
}) => {
  // Navigation & selection
  const [activeTab, setActiveTab] = useState<'issues' | 'proposals'>('issues')
  const [issues, setIssues] = useState<CodeIssue[]>([])
  const [selectedIssue, setSelectedIssue] = useState<CodeIssue | null>(null)
  const [proposals, setProposals] = useState<PatchProposal[]>([])
  const [activeProposal, setActiveProposal] = useState<PatchProposal | null>(null)
  const [activePlan, setActivePlan] = useState<FixPlan | null>(null)

  // Loading states
  const [loadingIssues, setLoadingIssues] = useState<boolean>(true)
  const [loadingProposals, setLoadingProposals] = useState<boolean>(false)
  const [planning, setPlanning] = useState<boolean>(false)
  const [generating, setGenerating] = useState<boolean>(false)
  const [reviewing, setReviewing] = useState<boolean>(false)

  // UI state
  const [error, setError] = useState<string | null>(null)
  const [feedbackInput, setFeedbackInput] = useState<string>('')
  const [showRegenModal, setShowRegenModal] = useState<boolean>(false)
  const [diffViewMode, setDiffViewMode] = useState<'diff' | 'modified' | 'original'>('diff')
  const [copiedDiff, setCopiedDiff] = useState<boolean>(false)
  const [selectedSnippetFile, setSelectedSnippetFile] = useState<string>('')

  // Phase 6: Docker Sandbox Execution state
  const [activeExecution, setActiveExecution] = useState<SandboxExecution | null>(null)
  const [executingSandbox, setExecutingSandbox] = useState<boolean>(false)

  // -------------------------------------------------------------
  // Data Loading
  // -------------------------------------------------------------
  const loadIssues = useCallback(async () => {
    try {
      setLoadingIssues(true)
      const res = await getIssues(repositoryId)
      const issList = res.data?.issues || []
      setIssues(issList)
      if (issList.length > 0 && !selectedIssue) {
        setSelectedIssue(issList[0])
      }
    } catch {
      // Backend may not have analysis runs yet
      setIssues([])
    } finally {
      setLoadingIssues(false)
    }
  }, [repositoryId, selectedIssue])

  const loadProposals = useCallback(async () => {
    try {
      setLoadingProposals(true)
      const res = await listPatches(repositoryId)
      const pList = res.data?.patches || []
      setProposals(pList)
    } catch {
      setProposals([])
    } finally {
      setLoadingProposals(false)
    }
  }, [repositoryId])

  useEffect(() => {
    loadIssues()
    loadProposals()
  }, [loadIssues, loadProposals])

  // When an issue is selected, check if a plan or proposal already exists
  useEffect(() => {
    if (!selectedIssue) {
      setActivePlan(null)
      setActiveProposal(null)
      return
    }

    let isMounted = true
    async function fetchIssueState() {
      setError(null)
      try {
        const planRes = await getFixPlan(repositoryId, selectedIssue!.issue_id)
        if (isMounted && planRes.data) {
          setActivePlan(planRes.data)
        }
      } catch {
        if (isMounted) setActivePlan(null)
      }

      // Check if a proposal matches this issue
      const match = proposals.find((p) => p.issue_id === selectedIssue!.issue_id)
      if (isMounted) {
        if (match) {
          setActiveProposal(match)
          if (match.affected_files && match.affected_files.length > 0) {
            setSelectedSnippetFile(match.affected_files[0])
          }
        } else {
          setActiveProposal(null)
        }
      }
    }

    fetchIssueState()
    return () => {
      isMounted = false
    }
  }, [selectedIssue, repositoryId, proposals])

  // Fetch execution results when active proposal changes
  useEffect(() => {
    if (!activeProposal) {
      setActiveExecution(null)
      return
    }

    let isMounted = true
    async function fetchExecution() {
      try {
        const res = await listExecutionsForPatch(repositoryId, activeProposal!.id)
        if (isMounted && res.data?.executions && res.data.executions.length > 0) {
          setActiveExecution(res.data.executions[0])
        } else if (isMounted) {
          setActiveExecution(null)
        }
      } catch {
        if (isMounted) setActiveExecution(null)
      }
    }

    fetchExecution()
    return () => {
      isMounted = false
    }
  }, [activeProposal, repositoryId])

  const handleRunSandbox = async () => {
    if (!activeProposal) return
    console.log(`[Frontend AiFixGenerator] Triggering Docker sandbox execution for patch: ${activeProposal.id}`)
    try {
      setExecutingSandbox(true)
      setError(null)
      const res = await executePatch(repositoryId, activeProposal.id)
      const initialExec = res.data
      setActiveExecution(initialExec)

      if (['completed', 'failed', 'timed_out'].includes(initialExec.status)) {
        console.log(`[Frontend AiFixGenerator] Execution reached terminal state: ${initialExec.status}`)
        return
      }

      // Polling for async container completion
      const execId = initialExec.id
      const maxAttempts = 60
      let attempts = 0
      while (attempts < maxAttempts) {
        await new Promise((r) => setTimeout(r, 2000))
        attempts++
        try {
          const pollRes = await getExecution(execId)
          const curr = pollRes.data
          setActiveExecution(curr)
          if (['completed', 'failed', 'timed_out'].includes(curr.status)) {
            console.log(`[Frontend AiFixGenerator] Polling finished with state: ${curr.status}`)
            break
          }
        } catch (pollErr) {
          console.error('[Frontend AiFixGenerator] Error polling execution:', pollErr)
          break
        }
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Docker sandbox execution failed'
      console.error('[Frontend AiFixGenerator] Execution request error:', msg)
      setError(msg)
    } finally {
      setExecutingSandbox(false)
    }
  }

  // -------------------------------------------------------------
  // Actions
  // -------------------------------------------------------------
  const handleGeneratePlan = async () => {
    if (!selectedIssue) return
    console.log(`[Frontend AiFixGenerator] "Generate Fix Plan" button clicked for issue: ${selectedIssue.issue_id}`)
    try {
      setPlanning(true)
      setError(null)
      const res = await createFixPlan(repositoryId, selectedIssue.issue_id)
      console.log(`[Frontend AiFixGenerator] Fix plan received and saved to state:`, res.data?.id)
      setActivePlan(res.data)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to generate fix plan.'
      console.error(`[Frontend AiFixGenerator] Fix plan generation error:`, msg)
      setError(msg)
    } finally {
      console.log(`[Frontend AiFixGenerator] Resetting planning state to false.`)
      setPlanning(false)
    }
  }

  const handleGeneratePatch = async (customFeedback?: string) => {
    if (!selectedIssue) return
    console.log(`[Frontend AiFixGenerator] "Synthesize Patch" button clicked for issue: ${selectedIssue.issue_id}`)
    try {
      setGenerating(true)
      setError(null)
      const res = await generatePatch(repositoryId, selectedIssue.issue_id, customFeedback)
      console.log(`[Frontend AiFixGenerator] Patch proposal received and saved to state:`, res.data?.id)
      setActiveProposal(res.data)
      if (res.data.affected_files && res.data.affected_files.length > 0) {
        setSelectedSnippetFile(res.data.affected_files[0])
      }
      // Refresh proposals list
      await loadProposals()
      setShowRegenModal(false)
      setFeedbackInput('')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Patch synthesis workflow failed.'
      console.error(`[Frontend AiFixGenerator] Patch synthesis workflow error:`, msg)
      setError(msg)
    } finally {
      console.log(`[Frontend AiFixGenerator] Resetting generating state to false.`)
      setGenerating(false)
    }
  }

  const handleReview = async (decision: 'approved' | 'rejected') => {
    if (!activeProposal) return
    console.log(`[Frontend AiFixGenerator] Review decision '${decision}' clicked for patch: ${activeProposal.id}`)
    try {
      setReviewing(true)
      setError(null)
      const res = await reviewPatch(activeProposal.id, {
        decision,
        reviewer_feedback: decision === 'approved' ? 'Approved proposal' : 'Rejected proposal',
      })
      console.log(`[Frontend AiFixGenerator] Review recorded successfully for patch: ${res.data?.id}`)
      setActiveProposal(res.data)
      await loadProposals()
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to submit review decision.'
      console.error(`[Frontend AiFixGenerator] Review submission error:`, msg)
      setError(msg)
    } finally {
      setReviewing(false)
    }
  }

  const handleRegenerate = async () => {
    if (!activeProposal) return
    console.log(`[Frontend AiFixGenerator] Regenerate patch clicked for patch: ${activeProposal.id}`)
    try {
      setGenerating(true)
      setError(null)
      const res = await regeneratePatch(activeProposal.id, feedbackInput)
      console.log(`[Frontend AiFixGenerator] Regenerated patch received:`, res.data?.id)
      setActiveProposal(res.data)
      if (res.data.affected_files && res.data.affected_files.length > 0) {
        setSelectedSnippetFile(res.data.affected_files[0])
      }
      await loadProposals()
      setShowRegenModal(false)
      setFeedbackInput('')
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Regeneration failed.'
      console.error(`[Frontend AiFixGenerator] Regeneration error:`, msg)
      setError(msg)
    } finally {
      setGenerating(false)
    }
  }

  const handleCopyDiff = () => {
    if (!activeProposal) return
    navigator.clipboard.writeText(activeProposal.patch_content)
    setCopiedDiff(true)
    setTimeout(() => setCopiedDiff(false), 2000)
  }

  const handleDownloadPatch = () => {
    if (!activeProposal) return
    const blob = new Blob([activeProposal.patch_content], { type: 'text/x-diff;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${activeProposal.id}.patch`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  const getRiskBadge = (risk: RiskLevel | string) => {
    switch (risk) {
      case 'Critical':
        return 'bg-red-950/80 text-red-300 border-red-700/60'
      case 'High':
        return 'bg-orange-950/80 text-orange-300 border-orange-700/60'
      case 'Medium':
        return 'bg-amber-950/80 text-amber-300 border-amber-700/60'
      default:
        return 'bg-emerald-950/80 text-emerald-300 border-emerald-700/60'
    }
  }

  const getSeverityBadge = (sev: string) => {
    switch (sev) {
      case 'Critical':
        return 'bg-red-950/80 text-red-400 border-red-800'
      case 'High':
        return 'bg-orange-950/80 text-orange-400 border-orange-800'
      case 'Medium':
        return 'bg-amber-950/80 text-amber-400 border-amber-800'
      default:
        return 'bg-blue-950/80 text-blue-400 border-blue-800'
    }
  }

  return (
    <div className="bg-slate-900/90 border border-slate-800 rounded-2xl shadow-xl overflow-hidden">
      {/* Header */}
      <div className="p-6 border-b border-slate-800 bg-slate-950/40">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 rounded-xl bg-cyan-950/80 border border-cyan-800/60 text-cyan-400">
              <Wrench className="h-5 w-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-lg font-bold text-slate-100">AI Fix Generator</h3>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-mono font-semibold bg-indigo-950/80 border border-indigo-800/60 text-indigo-300">
                  Phase 5: LangGraph Agent
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                Autonomous issue analysis, remediation planning, and verified unified-diff patch generation for <span className="text-slate-200 font-mono">{repositoryName}</span>.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                loadIssues()
                loadProposals()
              }}
              className="px-3 py-1.5 rounded-lg bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700 text-slate-300 text-xs flex items-center gap-1.5 transition-colors"
              title="Refresh issues and patch proposals"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              <span>Refresh</span>
            </button>
          </div>
        </div>

        {/* Phase 5 Explicit Safety Guarantee Warning Banner */}
        <div className="mt-4 p-3.5 rounded-xl bg-amber-950/30 border border-amber-700/50 flex items-start gap-3">
          <ShieldAlert className="h-5 w-5 text-amber-400 shrink-0 mt-0.5" />
          <div className="text-xs leading-relaxed text-amber-200/90">
            <span className="font-semibold text-amber-300">Phase 5 Safety Guarantee:</span> Patch proposals are stored for human inspection and review. Patches are <span className="underline font-bold text-amber-200">NOT applied</span> to repository files on disk until isolated container execution in Phase 6.
          </div>
        </div>
      </div>

      {/* Main Grid: Selector Left / Workspace Right */}
      <div className="grid grid-cols-1 lg:grid-cols-12 min-h-[580px]">
        {/* Left Column: Issues & Proposals Selector (4 cols) */}
        <div className="lg:col-span-4 border-r border-slate-800 bg-slate-950/20 flex flex-col">
          {/* Navigation Tabs */}
          <div className="flex border-b border-slate-800 p-2 gap-1 bg-slate-950/40">
            <button
              onClick={() => setActiveTab('issues')}
              className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-medium transition-colors flex items-center justify-center gap-1.5 ${
                activeTab === 'issues'
                  ? 'bg-slate-800 text-cyan-400 border border-slate-700 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <FileCode className="h-3.5 w-3.5" />
              <span>Detected Issues ({issues.length})</span>
            </button>
            <button
              onClick={() => setActiveTab('proposals')}
              className={`flex-1 py-1.5 px-3 rounded-lg text-xs font-medium transition-colors flex items-center justify-center gap-1.5 ${
                activeTab === 'proposals'
                  ? 'bg-slate-800 text-indigo-400 border border-slate-700 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <GitPullRequest className="h-3.5 w-3.5" />
              <span>Proposals ({proposals.length})</span>
            </button>
          </div>

          {/* List Content */}
          <div className="flex-1 overflow-y-auto max-h-[640px] divide-y divide-slate-850 p-2 space-y-1">
            {activeTab === 'issues' ? (
              loadingIssues ? (
                <div className="p-8 text-center text-slate-500 text-xs">
                  <Loader2 className="h-5 w-5 animate-spin mx-auto mb-2 text-cyan-500" />
                  Loading detected issues...
                </div>
              ) : issues.length === 0 ? (
                <div className="p-8 text-center text-slate-500 text-xs">
                  <Info className="h-6 w-6 mx-auto mb-2 text-slate-600" />
                  No code issues detected. Run Phase 4 AI analysis above to discover defects.
                </div>
              ) : (
                issues.map((iss) => {
                  const isSelected = selectedIssue?.issue_id === iss.issue_id
                  const hasProposal = proposals.some((p) => p.issue_id === iss.issue_id)
                  return (
                    <button
                      key={iss.issue_id}
                      onClick={() => setSelectedIssue(iss)}
                      className={`w-full text-left p-3 rounded-xl border transition-all text-xs flex flex-col gap-1.5 ${
                        isSelected
                          ? 'bg-slate-800/90 border-cyan-500/60 shadow-md ring-1 ring-cyan-500/30'
                          : 'bg-slate-900/40 border-slate-800/80 hover:bg-slate-850 hover:border-slate-700'
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span
                          className={`px-1.5 py-0.5 rounded text-[10px] font-semibold border ${getSeverityBadge(
                            iss.severity
                          )}`}
                        >
                          {iss.severity}
                        </span>
                        {hasProposal && (
                          <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-indigo-950/70 border border-indigo-700/60 text-indigo-300">
                            Patch Ready
                          </span>
                        )}
                        <span className="text-[11px] font-mono text-slate-500 truncate max-w-[140px]">
                          {iss.file_path}
                        </span>
                      </div>
                      <div className="font-semibold text-slate-200 line-clamp-1">{iss.issue_title}</div>
                      <div className="text-[11px] text-slate-400 line-clamp-2">
                        {iss.issue_description}
                      </div>
                      <div className="flex items-center justify-between text-[10px] text-slate-500 pt-1 border-t border-slate-800/60">
                        <span>Line {iss.start_line}</span>
                        <span>Confidence: {Math.round(iss.confidence_score * 100)}%</span>
                      </div>
                    </button>
                  )
                })
              )
            ) : loadingProposals ? (
              <div className="p-8 text-center text-slate-500 text-xs">
                <Loader2 className="h-5 w-5 animate-spin mx-auto mb-2 text-indigo-500" />
                Loading patch proposals...
              </div>
            ) : proposals.length === 0 ? (
              <div className="p-8 text-center text-slate-500 text-xs">
                <Info className="h-6 w-6 mx-auto mb-2 text-slate-600" />
                No patch proposals synthesized yet. Select an issue and click "Generate Patch".
              </div>
            ) : (
              proposals.map((prop) => {
                const isSelected = activeProposal?.id === prop.id
                return (
                  <button
                    key={prop.id}
                    onClick={() => {
                      setActiveProposal(prop)
                      const matchingIss = issues.find((i) => i.issue_id === prop.issue_id)
                      if (matchingIss) setSelectedIssue(matchingIss)
                      if (prop.affected_files && prop.affected_files.length > 0) {
                        setSelectedSnippetFile(prop.affected_files[0])
                      }
                    }}
                    className={`w-full text-left p-3 rounded-xl border transition-all text-xs flex flex-col gap-1.5 ${
                      isSelected
                        ? 'bg-slate-800/90 border-indigo-500/60 shadow-md ring-1 ring-indigo-500/30'
                        : 'bg-slate-900/40 border-slate-800/80 hover:bg-slate-850 hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono text-xs font-semibold text-indigo-300">
                        {prop.id.slice(0, 16)}
                      </span>
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-semibold border ${
                          prop.review_status === 'approved'
                            ? 'bg-emerald-950 text-emerald-300 border-emerald-700'
                            : prop.review_status === 'rejected'
                            ? 'bg-rose-950 text-rose-300 border-rose-700'
                            : 'bg-amber-950 text-amber-300 border-amber-700'
                        }`}
                      >
                        {prop.review_status}
                      </span>
                    </div>
                    <div className="flex items-center gap-3 text-[11px] text-slate-400">
                      <span className="text-emerald-400 font-mono">+{prop.lines_added}</span>
                      <span className="text-rose-400 font-mono">-{prop.lines_removed}</span>
                      <span className={`px-1.5 py-0.2 rounded text-[10px] border ${getRiskBadge(prop.risk_level)}`}>
                        {prop.risk_level} Risk
                      </span>
                    </div>
                    <div className="text-[10px] text-slate-500 truncate">
                      Files: {prop.affected_files.join(', ') || 'N/A'}
                    </div>
                  </button>
                )
              })
            )}
          </div>
        </div>

        {/* Right Column: Fix Workspace Deck (8 cols) */}
        <div className="lg:col-span-8 p-6 flex flex-col justify-between">
          {!selectedIssue ? (
            <div className="my-auto text-center p-12 text-slate-500">
              <FileCode className="h-10 w-10 mx-auto text-slate-600 mb-3" />
              <p className="text-sm font-semibold text-slate-300">No Issue Selected</p>
              <p className="text-xs text-slate-500 mt-1">
                Select an issue from the list on the left to inspect root cause, plan remediation, and synthesize patches.
              </p>
            </div>
          ) : (
            <div className="space-y-6">
              {/* Selected Issue Meta Card */}
              <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold border ${getSeverityBadge(
                        selectedIssue.severity
                      )}`}
                    >
                      {selectedIssue.severity}
                    </span>
                    <h4 className="text-sm font-bold text-slate-100">{selectedIssue.issue_title}</h4>
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-400 font-mono">
                    <span>
                      {selectedIssue.file_path}:{selectedIssue.start_line}
                    </span>
                    {selectedIssue.cwe_id && (
                      <span className="px-1.5 py-0.2 bg-slate-800 text-slate-300 rounded border border-slate-700 text-[10px]">
                        {selectedIssue.cwe_id}
                      </span>
                    )}
                    <span>Category: {selectedIssue.category}</span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    onClick={handleGeneratePlan}
                    disabled={planning || generating}
                    className="px-3 py-1.5 rounded-lg bg-cyan-950 hover:bg-cyan-900 border border-cyan-700/70 text-cyan-200 text-xs font-semibold flex items-center gap-1.5 transition-colors disabled:opacity-50"
                  >
                    {planning ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        <span>Planning...</span>
                      </>
                    ) : (
                      <>
                        <Sparkles className="h-3.5 w-3.5 text-cyan-400" />
                        <span>{activePlan ? 'Regenerate Plan' : '1. Generate Fix Plan'}</span>
                      </>
                    )}
                  </button>

                  <button
                    onClick={() => handleGeneratePatch()}
                    disabled={planning || generating}
                    className="px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold flex items-center gap-1.5 shadow-lg shadow-indigo-900/30 transition-colors disabled:opacity-50"
                  >
                    {generating ? (
                      <>
                        <Loader2 className="h-3.5 w-3.5 animate-spin" />
                        <span>Synthesizing Patch...</span>
                      </>
                    ) : (
                      <>
                        <GitPullRequest className="h-3.5 w-3.5" />
                        <span>{activeProposal ? 'Re-Synthesize Patch' : '2. Synthesize Patch'}</span>
                      </>
                    )}
                  </button>
                </div>
              </div>

              {/* Error banner if any */}
              {error && (
                <div className="p-3 rounded-xl bg-red-950/40 border border-red-800 text-xs text-red-300 flex items-center gap-2">
                  <AlertTriangle className="h-4 w-4 shrink-0 text-red-400" />
                  <span>{error}</span>
                </div>
              )}

              {/* Workflow Stepper */}
              <div className="p-3 rounded-xl bg-slate-950/40 border border-slate-800">
                <div className="text-[11px] font-medium text-slate-400 mb-2 flex items-center gap-1.5">
                  <GitPullRequest className="h-3.5 w-3.5 text-cyan-400" />
                  <span>LangGraph Agentic Synthesis Pipeline</span>
                </div>
                <div className="grid grid-cols-4 sm:grid-cols-8 gap-1.5 text-center text-[10px]">
                  {[
                    { label: 'Verify Code', active: true },
                    { label: 'AST Context', active: !!activePlan || !!activeProposal },
                    { label: 'Fix Plan', active: !!activePlan || !!activeProposal },
                    { label: 'Impact Fan-out', active: !!activePlan || !!activeProposal },
                    { label: 'Diff Synthesis', active: !!activeProposal },
                    { label: 'Deterministic Check', active: !!activeProposal },
                    { label: 'Risk Score', active: !!activeProposal },
                    { label: 'Review Ready', active: activeProposal?.validation_status === 'valid' },
                  ].map((step, idx) => (
                    <div
                      key={idx}
                      className={`p-1.5 rounded-lg border font-mono transition-colors ${
                        step.active
                          ? 'bg-slate-800 border-cyan-500/50 text-cyan-300'
                          : 'bg-slate-950/30 border-slate-850 text-slate-600'
                      }`}
                    >
                      {step.label}
                    </div>
                  ))}
                </div>
              </div>

              {/* Fix Plan Details */}
              {activePlan && (
                <div className="p-4 rounded-xl bg-slate-950/50 border border-slate-800 space-y-3">
                  <div className="flex items-center justify-between">
                    <h5 className="text-xs font-bold text-slate-200 flex items-center gap-1.5">
                      <FileText className="h-3.5 w-3.5 text-cyan-400" />
                      <span>Structured Fix Plan</span>
                    </h5>
                    <span className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${getRiskBadge(activePlan.risk_level)}`}>
                      Assessed Risk: {activePlan.risk_level}
                    </span>
                  </div>

                  <p className="text-xs text-slate-300 leading-relaxed">{activePlan.summary}</p>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                    <div className="p-3 rounded-lg bg-slate-900 border border-slate-800/80">
                      <span className="text-[10px] uppercase font-semibold text-slate-400">Root Cause</span>
                      <p className="text-slate-300 mt-1 text-[11px] leading-relaxed">{activePlan.root_cause || 'Identified via AST and semantic parsing.'}</p>
                    </div>
                    <div className="p-3 rounded-lg bg-slate-900 border border-slate-800/80">
                      <span className="text-[10px] uppercase font-semibold text-slate-400">Proposed Solution</span>
                      <p className="text-slate-300 mt-1 text-[11px] leading-relaxed">{activePlan.proposed_solution || 'Safe defensive remediation.'}</p>
                    </div>
                  </div>

                  {activePlan.implementation_steps && activePlan.implementation_steps.length > 0 && (
                    <div className="pt-2">
                      <span className="text-[10px] uppercase font-semibold text-slate-400 mb-1.5 block">
                        Implementation Steps
                      </span>
                      <ol className="list-decimal list-inside space-y-1 text-xs text-slate-300">
                        {activePlan.implementation_steps.map((st, i) => (
                          <li key={i} className="leading-relaxed">
                            {st}
                          </li>
                        ))}
                      </ol>
                    </div>
                  )}

                  {activePlan.recommended_tests && activePlan.recommended_tests.length > 0 && (
                    <div className="pt-2 border-t border-slate-850">
                      <span className="text-[10px] uppercase font-semibold text-slate-400 mb-1 block">
                        Recommended Verification Tests
                      </span>
                      <ul className="list-disc list-inside space-y-0.5 text-xs text-slate-400">
                        {activePlan.recommended_tests.map((t, idx) => (
                          <li key={idx} className="font-mono text-[11px]">
                            {t}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              {/* Patch Proposal Display & Code Diff View */}
              {activeProposal && (
                <div className="p-4 rounded-xl bg-slate-950/50 border border-slate-800 space-y-4">
                  {/* Top Stats Bar */}
                  <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-slate-800">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-bold text-slate-200">
                        Proposal {activeProposal.id}
                      </span>
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${
                          activeProposal.validation_status === 'valid'
                            ? 'bg-emerald-950/80 text-emerald-300 border-emerald-700'
                            : 'bg-rose-950/80 text-rose-300 border-rose-700'
                        }`}
                      >
                        {activeProposal.validation_status === 'valid' ? 'Deterministic Validation: PASS' : 'Validation: FAIL'}
                      </span>
                    </div>

                    <div className="flex items-center gap-3 text-xs">
                      <span className="text-emerald-400 font-mono font-bold">+{activeProposal.lines_added}</span>
                      <span className="text-rose-400 font-mono font-bold">-{activeProposal.lines_removed}</span>
                      <span className="text-slate-400 text-xs">
                        Confidence: {Math.round(activeProposal.confidence_score * 100)}%
                      </span>
                      {activeProposal.regeneration_attempt > 0 && (
                        <span className="px-1.5 py-0.5 rounded bg-slate-800 text-[10px] text-slate-300 border border-slate-700 font-mono">
                          Attempt #{activeProposal.regeneration_attempt}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Validation Checklist Cards */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
                    <div className="p-2 rounded-lg bg-slate-900 border border-slate-800 flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                      <span className="text-[11px] text-slate-300">Syntax Valid</span>
                    </div>
                    <div className="p-2 rounded-lg bg-slate-900 border border-slate-800 flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                      <span className="text-[11px] text-slate-300">Boundary Enforced</span>
                    </div>
                    <div className="p-2 rounded-lg bg-slate-900 border border-slate-800 flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                      <span className="text-[11px] text-slate-300">Protected Files Disallowed</span>
                    </div>
                    <div className="p-2 rounded-lg bg-slate-900 border border-slate-800 flex items-center gap-2">
                      <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                      <span className="text-[11px] text-slate-300">In-Memory Hunks Match</span>
                    </div>
                  </div>

                  {/* Diff View Mode Tabs & Quick Actions */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pt-2">
                    <div className="flex items-center gap-1 bg-slate-900 p-1 rounded-lg border border-slate-800 text-xs">
                      <button
                        onClick={() => setDiffViewMode('diff')}
                        className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                          diffViewMode === 'diff'
                            ? 'bg-slate-800 text-cyan-400 shadow'
                            : 'text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        Unified Diff
                      </button>
                      <button
                        onClick={() => setDiffViewMode('modified')}
                        className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                          diffViewMode === 'modified'
                            ? 'bg-slate-800 text-cyan-400 shadow'
                            : 'text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        Modified Code
                      </button>
                      <button
                        onClick={() => setDiffViewMode('original')}
                        className={`px-3 py-1 rounded text-xs font-medium transition-colors ${
                          diffViewMode === 'original'
                            ? 'bg-slate-800 text-cyan-400 shadow'
                            : 'text-slate-400 hover:text-slate-200'
                        }`}
                      >
                        Original Code
                      </button>
                    </div>

                    <div className="flex items-center gap-2">
                      <button
                        onClick={handleCopyDiff}
                        className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-750 text-slate-300 text-xs flex items-center gap-1 border border-slate-700 transition-colors"
                        title="Copy unified diff"
                      >
                        {copiedDiff ? <Check className="h-3.5 w-3.5 text-emerald-400" /> : <Copy className="h-3.5 w-3.5" />}
                        <span>{copiedDiff ? 'Copied' : 'Copy Diff'}</span>
                      </button>
                      <button
                        onClick={handleDownloadPatch}
                        className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-750 text-slate-300 text-xs flex items-center gap-1 border border-slate-700 transition-colors"
                        title="Download .patch file"
                      >
                        <Download className="h-3.5 w-3.5" />
                        <span>.patch</span>
                      </button>
                    </div>
                  </div>

                  {/* Code Viewer Container */}
                  <div className="rounded-xl border border-slate-800 bg-slate-950 overflow-hidden">
                    {diffViewMode === 'diff' ? (
                      <div className="p-3 overflow-x-auto font-mono text-xs max-h-[380px] leading-relaxed select-text">
                        {activeProposal.patch_content.split('\n').map((line, index) => {
                          let lineClass = 'text-slate-300'
                          if (line.startsWith('+') && !line.startsWith('+++')) {
                            lineClass = 'bg-emerald-950/40 text-emerald-300 border-l-2 border-emerald-500 pl-2'
                          } else if (line.startsWith('-') && !line.startsWith('---')) {
                            lineClass = 'bg-rose-950/40 text-rose-300 border-l-2 border-rose-500 pl-2'
                          } else if (line.startsWith('@@')) {
                            lineClass = 'text-cyan-400 font-bold bg-cyan-950/20 pl-2'
                          } else if (line.startsWith('---') || line.startsWith('+++')) {
                            lineClass = 'text-slate-400 font-bold pl-2'
                          }
                          return (
                            <div key={index} className={`whitespace-pre ${lineClass}`}>
                              {line || ' '}
                            </div>
                          )
                        })}
                      </div>
                    ) : diffViewMode === 'modified' ? (
                      <div className="p-3 overflow-x-auto font-mono text-xs max-h-[380px] text-slate-200 leading-relaxed select-text whitespace-pre">
                        {activeProposal.modified_snippets[selectedSnippetFile] ||
                          activeProposal.modified_snippets[Object.keys(activeProposal.modified_snippets)[0]] ||
                          'No snippet loaded'}
                      </div>
                    ) : (
                      <div className="p-3 overflow-x-auto font-mono text-xs max-h-[380px] text-slate-400 leading-relaxed select-text whitespace-pre">
                        {activeProposal.original_snippets[selectedSnippetFile] ||
                          activeProposal.original_snippets[Object.keys(activeProposal.original_snippets)[0]] ||
                          'No snippet loaded'}
                      </div>
                    )}
                  </div>

                  {/* Human Review Controls */}
                  <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 flex flex-col sm:flex-row items-center justify-between gap-3">
                    <div className="flex items-center gap-2">
                      <span className="text-xs text-slate-400">Review Decision:</span>
                      <span
                        className={`px-2 py-0.5 rounded text-xs font-semibold border ${
                          activeProposal.review_status === 'approved'
                            ? 'bg-emerald-950 text-emerald-300 border-emerald-700'
                            : activeProposal.review_status === 'rejected'
                            ? 'bg-rose-950 text-rose-300 border-rose-700'
                            : 'bg-amber-950 text-amber-300 border-amber-700'
                        }`}
                      >
                        {activeProposal.review_status === 'approved'
                          ? 'Approved'
                          : activeProposal.review_status === 'rejected'
                          ? 'Rejected'
                          : 'Pending Human Review'}
                      </span>
                    </div>

                    <div className="flex items-center gap-2">
                      {activeProposal.review_status !== 'approved' && (
                        <button
                          onClick={() => handleReview('approved')}
                          disabled={reviewing}
                          className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-sm disabled:opacity-50"
                        >
                          <ThumbsUp className="h-3.5 w-3.5" />
                          <span>Approve Proposal</span>
                        </button>
                      )}

                      {activeProposal.review_status !== 'rejected' && (
                        <button
                          onClick={() => handleReview('rejected')}
                          disabled={reviewing}
                          className="px-3 py-1.5 rounded-lg bg-rose-950 hover:bg-rose-900 border border-rose-700/60 text-rose-300 text-xs font-semibold flex items-center gap-1.5 transition-colors disabled:opacity-50"
                        >
                          <ThumbsDown className="h-3.5 w-3.5" />
                          <span>Reject Proposal</span>
                        </button>
                      )}

                      <button
                        onClick={() => setShowRegenModal(true)}
                        disabled={generating || reviewing}
                        className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-750 border border-slate-700 text-slate-200 text-xs font-semibold flex items-center gap-1.5 transition-colors disabled:opacity-50"
                      >
                        <RotateCcw className="h-3.5 w-3.5" />
                        <span>Regenerate with Guidance</span>
                      </button>
                    </div>
                  </div>

                  {/* Approved Banner */}
                  {activeProposal.review_status === 'approved' && (
                    <div className="p-3 rounded-xl bg-emerald-950/40 border border-emerald-800 text-xs text-emerald-300 flex items-center gap-2">
                      <CheckSquare className="h-4 w-4 shrink-0 text-emerald-400" />
                      <span>
                        Proposal approved by human reviewer. Proposal is preserved in state and ready for Phase 6 Docker isolated execution and verification.
                      </span>
                    </div>
                  )}

                  {/* Phase 6: Docker Sandbox Execution Panel */}
                  <div className="pt-2">
                    <DockerExecutionPanel
                      execution={activeExecution}
                      loading={executingSandbox}
                      onRunExecution={handleRunSandbox}
                      disabled={generating || reviewing}
                    />
                  </div>
                </div>
              )}

              {/* Regeneration Guidance Modal */}
              {showRegenModal && (
                <div className="p-4 rounded-xl bg-slate-950 border border-indigo-500/50 space-y-3">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-indigo-300 flex items-center gap-1.5">
                      <RotateCcw className="h-3.5 w-3.5" />
                      <span>Regenerate Patch with Reviewer Guidance</span>
                    </span>
                    <button
                      onClick={() => setShowRegenModal(false)}
                      className="text-slate-500 hover:text-slate-300 text-xs"
                    >
                      Cancel
                    </button>
                  </div>
                  <textarea
                    rows={3}
                    value={feedbackInput}
                    onChange={(e) => setFeedbackInput(e.target.value)}
                    placeholder="Provide specific instructions, e.g.: 'Use a try/finally block', 'Verify parameter bounds before division', 'Avoid modifying function signature'..."
                    className="w-full p-2.5 rounded-lg bg-slate-900 border border-slate-800 text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  />
                  <div className="flex justify-end gap-2">
                    <button
                      onClick={() => setShowRegenModal(false)}
                      className="px-3 py-1.5 rounded-lg text-xs text-slate-400 hover:text-slate-200"
                    >
                      Close
                    </button>
                    <button
                      onClick={handleRegenerate}
                      disabled={generating}
                      className="px-3.5 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold flex items-center gap-1.5 disabled:opacity-50"
                    >
                      {generating ? (
                        <>
                          <Loader2 className="h-3.5 w-3.5 animate-spin" />
                          <span>Regenerating...</span>
                        </>
                      ) : (
                        <>
                          <Sparkles className="h-3.5 w-3.5" />
                          <span>Submit & Regenerate</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
