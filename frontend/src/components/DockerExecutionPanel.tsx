import React, { useState } from 'react'
import {
  Box,
  Play,
  Terminal,
  Cpu,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  Loader2,
  ChevronDown,
  ChevronUp,
  Copy,
  Check,
  Server,
  Layers,
} from 'lucide-react'
import type { SandboxExecution, ExecutionStatus, ExecutionVerdict } from '../types'

interface DockerExecutionPanelProps {
  execution: SandboxExecution | null
  loading: boolean
  onRunExecution: () => void
  disabled?: boolean
}

export const DockerExecutionPanel: React.FC<DockerExecutionPanelProps> = ({
  execution,
  loading,
  onRunExecution,
  disabled = false,
}) => {
  const [showLogs, setShowLogs] = useState<boolean>(true)
  const [showDetails, setShowDetails] = useState<boolean>(false)
  const [copiedLogs, setCopiedLogs] = useState<boolean>(false)

  const handleCopyLogs = () => {
    if (!execution?.logs) return
    navigator.clipboard.writeText(execution.logs)
    setCopiedLogs(true)
    setTimeout(() => setCopiedLogs(false), 2000)
  }

  // Verdict display metadata
  const getVerdictBadge = (verdict?: ExecutionVerdict | string | null) => {
    const v = (verdict || '').toLowerCase()
    switch (v) {
      case 'success':
        return {
          label: 'VERIFIED SUCCESS',
          className: 'bg-emerald-950/80 text-emerald-300 border-emerald-600/60',
          icon: <CheckCircle2 className="h-4 w-4 text-emerald-400" />,
          desc: 'The patch was applied cleanly and all tests passed inside the isolated container.',
        }
      case 'regression':
        return {
          label: 'REGRESSION DETECTED',
          className: 'bg-rose-950/80 text-rose-300 border-rose-600/60',
          icon: <XCircle className="h-4 w-4 text-rose-400" />,
          desc: 'The patch broke previously passing tests. Further refinement is required.',
        }
      case 'test_failure':
        return {
          label: 'TESTS FAILED',
          className: 'bg-rose-950/80 text-rose-300 border-rose-600/60',
          icon: <XCircle className="h-4 w-4 text-rose-400" />,
          desc: 'Automated test suite reported failures after patch application.',
        }
      case 'patch_application_failed':
        return {
          label: 'PATCH APPLICATION FAILED',
          className: 'bg-rose-950/80 text-rose-300 border-rose-600/60',
          icon: <AlertTriangle className="h-4 w-4 text-rose-400" />,
          desc: 'Unified diff could not be applied cleanly to the repository workspace.',
        }
      case 'dependency_error':
        return {
          label: 'DEPENDENCY ERROR',
          className: 'bg-amber-950/80 text-amber-300 border-amber-600/60',
          icon: <AlertTriangle className="h-4 w-4 text-amber-400" />,
          desc: 'Failure during dependency inspection or offline environment setup.',
        }
      case 'timeout':
        return {
          label: 'TIMED OUT',
          className: 'bg-amber-950/80 text-amber-300 border-amber-600/60',
          icon: <AlertTriangle className="h-4 w-4 text-amber-400" />,
          desc: 'Execution exceeded maximum sandbox timeout threshold.',
        }
      case 'environment_error':
        return {
          label: 'DOCKER DAEMON UNAVAILABLE',
          className: 'bg-amber-950/80 text-amber-300 border-amber-600/60',
          icon: <Server className="h-4 w-4 text-amber-400" />,
          desc: 'Docker daemon is not running on the host. Untrusted code execution was safely prevented to protect your host system.',
        }
      case 'no_tests':
        return {
          label: 'NO TESTS DISCOVERED',
          className: 'bg-slate-800/80 text-slate-300 border-slate-600/60',
          icon: <Layers className="h-4 w-4 text-slate-400" />,
          desc: 'Patch was applied inside the container, but no test runner configuration was detected.',
        }
      default:
        return {
          label: 'PENDING VERDICT',
          className: 'bg-slate-800/80 text-slate-400 border-slate-700',
          icon: <Loader2 className="h-4 w-4 animate-spin text-cyan-400" />,
          desc: 'Container sandbox execution in progress...',
        }
    }
  }

  // Stepper helper
  const getStepStatus = (
    currentStatus?: ExecutionStatus,
    targetStep?: 'init' | 'patch' | 'tests' | 'done'
  ) => {
    if (!currentStatus) return 'pending'
    const s = currentStatus.toLowerCase()

    const stepOrder: Record<string, number> = {
      pending: 0,
      initializing: 1,
      preparing: 1,
      applying_patch: 2,
      installing_dependencies: 2,
      running_tests: 3,
      completed: 4,
      failed: 4,
      timed_out: 4,
    }

    const currentOrder = stepOrder[s] || 0
    let targetOrder = 0
    if (targetStep === 'init') targetOrder = 1
    if (targetStep === 'patch') targetOrder = 2
    if (targetStep === 'tests') targetOrder = 3
    if (targetStep === 'done') targetOrder = 4

    if (currentOrder > targetOrder) return 'completed'
    if (currentOrder === targetOrder) {
      if (['failed', 'timed_out'].includes(s)) return 'error'
      return 'active'
    }
    return 'pending'
  }

  const activeVerdict =
    execution?.comparison?.verdict ||
    (execution?.error_message?.toLowerCase().includes('docker') ? 'environment_error' : null)
  const verdictMeta = getVerdictBadge(activeVerdict)

  return (
    <div className="rounded-xl border border-indigo-500/30 bg-slate-900/90 shadow-xl overflow-hidden space-y-4 p-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-slate-800 pb-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-lg bg-indigo-950/70 border border-indigo-700/50 text-indigo-400">
            <Box className="h-5 w-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h4 className="text-sm font-bold text-slate-100">Docker Sandbox Validation Engine</h4>
              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-semibold bg-indigo-950 text-indigo-300 border border-indigo-800">
                Phase 6
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Secure in-container patch verification with Pytest/Jest & strict host isolation.
            </p>
          </div>
        </div>

        <button
          onClick={onRunExecution}
          disabled={disabled || loading}
          className="px-4 py-2 rounded-lg bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 text-white text-xs font-semibold flex items-center justify-center gap-2 shadow-md transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
        >
          {loading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin text-white" />
              <span>Executing in Sandbox...</span>
            </>
          ) : (
            <>
              <Play className="h-4 w-4 fill-white" />
              <span>{execution ? 'Re-run in Sandbox' : 'Execute in Docker Sandbox'}</span>
            </>
          )}
        </button>
      </div>

      {/* 4-Step Pipeline Stepper */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 pb-2">
        {[
          { key: 'init' as const, label: '1. Isolation & Setup' },
          { key: 'patch' as const, label: '2. Patch Application' },
          { key: 'tests' as const, label: '3. Test Execution' },
          { key: 'done' as const, label: '4. Verification' },
        ].map((step) => {
          const status = getStepStatus(execution?.status, step.key)
          let pillStyle = 'bg-slate-950/60 border-slate-800 text-slate-500'
          if (status === 'completed') {
            pillStyle = 'bg-emerald-950/40 border-emerald-700/60 text-emerald-300'
          } else if (status === 'active') {
            pillStyle = 'bg-indigo-950/70 border-indigo-500/70 text-indigo-300 shadow-sm ring-1 ring-indigo-500/30'
          } else if (status === 'error') {
            pillStyle = 'bg-rose-950/50 border-rose-700/60 text-rose-300'
          }

          return (
            <div
              key={step.key}
              className={`p-2 rounded-lg border text-[11px] font-medium flex items-center justify-between transition-colors ${pillStyle}`}
            >
              <span className="truncate">{step.label}</span>
              {status === 'completed' && <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400 shrink-0" />}
              {status === 'active' && <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-400 shrink-0" />}
              {status === 'error' && <XCircle className="h-3.5 w-3.5 text-rose-400 shrink-0" />}
            </div>
          )
        })}
      </div>

      {/* Stepper Progress */}
      {loading && (
        <div className="p-3.5 rounded-lg bg-slate-950/70 border border-slate-800 flex items-center justify-between text-xs">
          <div className="flex items-center gap-2 text-indigo-400">
            <Loader2 className="h-4 w-4 animate-spin" />
            <span className="font-semibold capitalize">
              Current Stage: {execution?.status.toLowerCase().replace('_', ' ') || 'Starting sandbox...'}
            </span>
          </div>
          <span className="text-[11px] font-mono text-slate-400">
            {execution?.duration_seconds ? `${execution.duration_seconds.toFixed(1)}s elapsed` : 'Running isolated container'}
          </span>
        </div>
      )}

      {/* Verdict / Status Card */}
      {execution && (
        <div className={`p-4 rounded-xl border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 ${verdictMeta.className}`}>
          <div className="flex items-start sm:items-center gap-3">
            <div className="p-2 rounded-lg bg-black/20 shrink-0 mt-0.5 sm:mt-0">
              {verdictMeta.icon}
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold tracking-wide">{verdictMeta.label}</span>
                <span className="text-[10px] opacity-75 font-mono">
                  ({execution.duration_seconds.toFixed(2)}s)
                </span>
              </div>
              <p className="text-xs mt-0.5 opacity-90">{verdictMeta.desc}</p>
            </div>
          </div>

          {execution.error_message && (
            <div className="text-[11px] font-mono px-3 py-1.5 rounded bg-black/40 text-rose-200 border border-rose-500/30 max-w-md truncate">
              {execution.error_message}
            </div>
          )}
        </div>
      )}

      {/* Before / After Comparison Table */}
      {execution?.comparison && (
        <div className="rounded-xl border border-slate-800 bg-slate-950/60 overflow-hidden">
          <div className="px-4 py-2.5 bg-slate-900/90 border-b border-slate-800 flex items-center justify-between">
            <span className="text-xs font-bold text-slate-200 flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-cyan-400" />
              Automated Test Verification (Before vs After)
            </span>
            <span
              className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${
                execution.comparison.tests_fixed > 0
                  ? 'bg-emerald-950 text-emerald-300 border-emerald-700'
                  : execution.comparison.tests_regressed > 0
                  ? 'bg-rose-950 text-rose-300 border-rose-700'
                  : 'bg-slate-800 text-slate-400 border-slate-700'
              }`}
            >
              {execution.comparison.summary}
            </span>
          </div>

          <div className="p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Baseline Test Card */}
            <div className="p-3.5 rounded-lg bg-slate-900/60 border border-slate-800/80 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-slate-300">Baseline (Pre-Patch)</span>
                <span
                  className={`px-1.5 py-0.5 rounded text-[10px] font-mono border ${
                    execution.comparison.baseline_failed === 0 && execution.comparison.baseline_passed > 0
                      ? 'bg-emerald-950 text-emerald-300 border-emerald-700'
                      : 'bg-rose-950 text-rose-300 border-rose-700'
                  }`}
                >
                  {execution.comparison.baseline_status?.toUpperCase() || (execution.comparison.baseline_failed === 0 ? 'PASSED' : 'FAILED')}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-center text-xs">
                <div className="p-2 rounded bg-slate-950/80 border border-slate-800">
                  <div className="text-emerald-400 font-mono font-bold">
                    {execution.comparison.baseline_passed}
                  </div>
                  <div className="text-[10px] text-slate-400">Passed</div>
                </div>
                <div className="p-2 rounded bg-slate-950/80 border border-slate-800">
                  <div className="text-rose-400 font-mono font-bold">
                    {execution.comparison.baseline_failed}
                  </div>
                  <div className="text-[10px] text-slate-400">Failed</div>
                </div>
                <div className="p-2 rounded bg-slate-950/80 border border-slate-800">
                  <div className="text-slate-300 font-mono font-bold">
                    {execution.baseline_result?.duration_seconds ? `${execution.baseline_result.duration_seconds.toFixed(2)}s` : '0.00s'}
                  </div>
                  <div className="text-[10px] text-slate-400">Duration</div>
                </div>
              </div>
            </div>

            {/* Patched Test Card */}
            <div className="p-3.5 rounded-lg bg-slate-900/60 border border-slate-800/80 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold text-indigo-300">Patched (Post-Patch)</span>
                <span
                  className={`px-1.5 py-0.5 rounded text-[10px] font-mono border ${
                    execution.comparison.patched_failed === 0 && execution.comparison.patched_passed > 0
                      ? 'bg-emerald-950 text-emerald-300 border-emerald-700'
                      : 'bg-rose-950 text-rose-300 border-rose-700'
                  }`}
                >
                  {execution.comparison.patched_status?.toUpperCase() || (execution.comparison.patched_failed === 0 ? 'PASSED' : 'FAILED')}
                </span>
              </div>
              <div className="grid grid-cols-3 gap-2 text-center text-xs">
                <div className="p-2 rounded bg-slate-950/80 border border-slate-800">
                  <div className="text-emerald-400 font-mono font-bold">
                    {execution.comparison.patched_passed}
                  </div>
                  <div className="text-[10px] text-slate-400">Passed</div>
                </div>
                <div className="p-2 rounded bg-slate-950/80 border border-slate-800">
                  <div className="text-rose-400 font-mono font-bold">
                    {execution.comparison.patched_failed}
                  </div>
                  <div className="text-[10px] text-slate-400">Failed</div>
                </div>
                <div className="p-2 rounded bg-slate-950/80 border border-slate-800">
                  <div className="text-slate-300 font-mono font-bold">
                    {execution.patched_result?.duration_seconds ? `${execution.patched_result.duration_seconds.toFixed(2)}s` : '0.00s'}
                  </div>
                  <div className="text-[10px] text-slate-400">Duration</div>
                </div>
              </div>
            </div>
          </div>

          {/* Test metrics tags */}
          {(execution.comparison.tests_fixed > 0 || execution.comparison.tests_regressed > 0) && (
            <div className="px-4 pb-3 flex flex-wrap gap-2 text-xs">
              {execution.comparison.tests_fixed > 0 && (
                <span className="px-2 py-0.5 rounded bg-emerald-950/60 border border-emerald-700/60 text-emerald-300 font-mono text-[10px]">
                  + Resolved: {execution.comparison.tests_fixed} failing test(s) fixed
                </span>
              )}
              {execution.comparison.tests_regressed > 0 && (
                <span className="px-2 py-0.5 rounded bg-rose-950/60 border border-rose-700/60 text-rose-300 font-mono text-[10px]">
                  - Regression: {execution.comparison.tests_regressed} test(s) failed
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Ephemeral Container Metadata Toggle */}
      {execution && (
        <div className="space-y-2">
          <button
            onClick={() => setShowDetails(!showDetails)}
            className="w-full flex items-center justify-between px-3.5 py-2 rounded-lg bg-slate-950/50 border border-slate-800 hover:border-slate-700 text-xs text-slate-400 transition-colors cursor-pointer"
          >
            <span className="flex items-center gap-2">
              <Cpu className="h-3.5 w-3.5 text-indigo-400" />
              <span>Sandbox Container & Security Specifications</span>
            </span>
            {showDetails ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
          </button>

          {showDetails && (
            <div className="p-3.5 rounded-lg bg-slate-950 border border-slate-800 grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div>
                <span className="text-[10px] text-slate-500 block">CONTAINER ID</span>
                <span className="font-mono text-slate-300 text-[11px]">
                  {execution.container_id ? execution.container_id.slice(0, 12) : 'ephemeral-destroyed'}
                </span>
              </div>
              <div>
                <span className="text-[10px] text-slate-500 block">BASE LANGUAGE</span>
                <span className="font-mono text-slate-300 text-[11px]">{execution.language || 'python'}</span>
              </div>
              <div>
                <span className="text-[10px] text-slate-500 block">ISOLATION MODE</span>
                <span className="font-mono text-emerald-400 text-[11px]">
                  Airgapped (network_mode=none)
                </span>
              </div>
              <div>
                <span className="text-[10px] text-slate-500 block">PATCH APPLIED</span>
                <span className="font-mono text-slate-300 text-[11px]">
                  {execution.patch_applied ? 'Yes (Clean)' : 'No'} ({execution.modified_files.length} files)
                </span>
              </div>
            </div>
          )}
        </div>
      )}

      {/* In-Container Execution Logs */}
      {execution && execution.logs && (
        <div className="rounded-xl border border-slate-800 bg-slate-950 overflow-hidden">
          <div className="px-3.5 py-2 bg-slate-900 border-b border-slate-800 flex items-center justify-between">
            <button
              onClick={() => setShowLogs(!showLogs)}
              className="flex items-center gap-2 text-xs font-semibold text-slate-300 hover:text-white transition-colors cursor-pointer"
            >
              <Terminal className="h-3.5 w-3.5 text-cyan-400" />
              <span>Container Execution Logs</span>
              {showLogs ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
            </button>

            <button
              onClick={handleCopyLogs}
              className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-750 text-slate-300 text-[11px] flex items-center gap-1 border border-slate-700 transition-colors cursor-pointer"
            >
              {copiedLogs ? (
                <>
                  <Check className="h-3 w-3 text-emerald-400" />
                  <span className="text-emerald-400">Copied</span>
                </>
              ) : (
                <>
                  <Copy className="h-3 w-3" />
                  <span>Copy Logs</span>
                </>
              )}
            </button>
          </div>

          {showLogs && (
            <div className="p-3.5 max-h-[320px] overflow-y-auto font-mono text-[11px] leading-relaxed text-slate-300 bg-slate-950 space-y-0.5 select-text">
              {execution.logs.split('\n').map((line, i) => {
                let colorClass = 'text-slate-300'
                if (line.includes('[SandboxRunner]') || line.includes('[ContainerManager]')) {
                  colorClass = 'text-cyan-400'
                } else if (line.includes('PASSED') || line.includes('SUCCESS') || line.includes('applied')) {
                  colorClass = 'text-emerald-400'
                } else if (line.includes('FAILED') || line.includes('ERROR') || line.includes('ABORTED')) {
                  colorClass = 'text-rose-400'
                } else if (line.includes('WARNING') || line.includes('SKIPPED')) {
                  colorClass = 'text-amber-400'
                }
                return (
                  <div key={i} className={`whitespace-pre-wrap ${colorClass}`}>
                    {line || ' '}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}

      {/* Safety Notice Banner */}
      <div className="flex items-center gap-2 text-[11px] text-slate-500 px-1 pt-1">
        <ShieldCheck className="h-3.5 w-3.5 text-indigo-400 shrink-0" />
        <span>
          Untrusted code execution guarantee: All testing and patch application is executed exclusively inside ephemeral, network-isolated containers. Host system is never touched.
        </span>
      </div>
    </div>
  )
}
