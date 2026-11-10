import React, { useState, useEffect, useCallback } from 'react'
import { HealthCard } from '../components/HealthCard'
import { RoadmapCard } from '../components/RoadmapCard'
import { IngestionCard } from '../components/IngestionCard'
import { RepositoryCard } from '../components/RepositoryCard'
import { DirectoryTree } from '../components/DirectoryTree'
import { RecentRepositories } from '../components/RecentRepositories'
import { CodeIntelligenceSection } from '../components/CodeIntelligenceSection'
import { CodeSearchSection } from '../components/CodeSearchSection'
import { CodeAnalysisSection } from '../components/CodeAnalysisSection'
import { AiFixGeneratorSection } from '../components/AiFixGeneratorSection'
import type { HealthResponse, RoadmapPhase, RepositoryDetail, RepositorySummary } from '../types'
import { listRepositories, getRepositoryDetails } from '../services/repository'
import { Layers, ShieldCheck, Cpu, Code2, GitFork, FolderGit2 } from 'lucide-react'

interface DashboardProps {
  health: HealthResponse | null
  loading: boolean
  error: string | null
  lastChecked: Date | null
  onRefresh: () => void
}

const PHASES: RoadmapPhase[] = [
  {
    id: 0,
    title: 'Architecture & Foundation',
    description: 'System design, monorepo structure, FastAPI baseline, React Vite frontend, and verification harness.',
    status: 'completed',
    tag: 'FastAPI + React 19',
  },
  {
    id: 1,
    title: 'Repository Ingestion & Storage',
    description: 'ZIP extraction with path traversal guards, GitHub clone via GitPython, and .gitignore file walker.',
    status: 'completed',
    tag: 'GitPython + Storage',
  },
  {
    id: 2,
    title: 'Code Intelligence & AST Parsing',
    description: 'Tree-sitter and Python AST syntax tree extraction, symbol tables, and call graph resolution.',
    status: 'completed',
    tag: 'Tree-sitter + AST',
  },
  {
    id: 3,
    title: 'pgvector & Hybrid Code RAG',
    description: 'AST-aligned code chunking, Google Gemini text-embedding-004 vectors, and HNSW cosine similarity search.',
    status: 'completed',
    tag: 'PostgreSQL + pgvector',
  },
  {
    id: 4,
    title: 'AI Code Analysis & Bug Detection',
    description: 'Gemini structured prompt orchestration for logic bugs, OWASP security vulnerabilities, and code smells.',
    status: 'completed',
    tag: 'Gemini Pro + JSON Schema',
  },
  {
    id: 5,
    title: 'Agentic Planning & Patch Synthesis',
    description: 'LangGraph multi-step repair plan generation, dependency ordering, and multi-file unified diff synthesis.',
    status: 'completed',
    tag: 'LangGraph Planner',
  },
  {
    id: 6,
    title: 'Docker Sandbox Execution',
    description: 'Ephemeral container lifecycle, strict offline network isolation, CPU/RAM quotas, and Pytest log streaming.',
    status: 'completed',
    tag: 'Docker API + Pytest',
  },
  {
    id: 7,
    title: 'Self-Correction Feedback Loop',
    description: 'Autonomous traceback analysis, assertion diagnostic synthesis, and bounded repair iteration loops.',
    status: 'planned',
    tag: 'Cyclic StateGraph',
  },
  {
    id: 8,
    title: 'Interactive Code Review UI',
    description: 'Side-by-side git diff viewer, live SSE agent reasoning stream, and exportable engineering reports.',
    status: 'planned',
    tag: 'DiffViewer + SSE',
  },
]

export const Dashboard: React.FC<DashboardProps> = ({
  health,
  loading: healthLoading,
  error: healthError,
  lastChecked,
  onRefresh,
}) => {
  const [repositories, setRepositories] = useState<RepositorySummary[]>([])
  const [reposLoading, setReposLoading] = useState<boolean>(true)
  const [activeRepo, setActiveRepo] = useState<RepositoryDetail | null>(null)
  const [activeLoading, setActiveLoading] = useState<boolean>(false)

  const fetchRepos = useCallback(async () => {
    try {
      setReposLoading(true)
      const res = await listRepositories()
      setRepositories(res.data)
      if (res.data.length > 0 && !activeRepo) {
        const first = res.data[0]
        const detailRes = await getRepositoryDetails(first.id)
        setActiveRepo(detailRes.data)
      }
    } catch {
      // Backend may be offline during initial boot
    } finally {
      setReposLoading(false)
    }
  }, [activeRepo])

  useEffect(() => {
    let ignore = false

    async function loadInitial() {
      try {
        const res = await listRepositories()
        if (!ignore) {
          setRepositories(res.data)
          if (res.data.length > 0 && !activeRepo) {
            const detailRes = await getRepositoryDetails(res.data[0].id)
            if (!ignore) {
              setActiveRepo(detailRes.data)
            }
          }
        }
      } catch {
        // Backend may be offline during initial boot
      } finally {
        if (!ignore) {
          setReposLoading(false)
        }
      }
    }

    loadInitial()

    return () => {
      ignore = true
    }
  }, [activeRepo])

  const handleSelectRepo = async (repoId: string) => {
    try {
      setActiveLoading(true)
      const res = await getRepositoryDetails(repoId)
      setActiveRepo(res.data)
    } catch (err: unknown) {
      console.error('Failed to load repository details:', err)
    } finally {
      setActiveLoading(false)
    }
  }

  const handleIngestionSuccess = (repo: RepositoryDetail) => {
    setActiveRepo(repo)
    fetchRepos()
  }

  return (
    <div className="space-y-8">
      {/* Hero Section */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-slate-900 via-slate-900/90 to-blue-950/40 p-8 border border-slate-800 shadow-2xl">
        <div className="relative z-10 max-w-3xl">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-cyan-950/80 border border-cyan-800/60 text-cyan-400 text-xs font-semibold mb-4">
            <Cpu className="h-3.5 w-3.5" />
            <span>Autonomous Software Engineer Platform</span>
          </div>
          <h1 className="text-3xl sm:text-4xl font-extrabold text-slate-100 tracking-tight">
            Analyze, Repair & Verify Codebases with Agentic Intelligence
          </h1>
          <p className="mt-3 text-sm sm:text-base text-slate-400 leading-relaxed">
            RepoPilot AI ingests full repositories via ZIP archives or public GitHub clones, indexes directory structures, extracts symbols, detects programming languages, and prepares code for multi-agent reasoning.
          </p>

          <div className="mt-6 flex flex-wrap gap-4 text-xs font-mono text-slate-300">
            <div className="flex items-center gap-1.5 bg-slate-950/70 border border-slate-800 px-3 py-1.5 rounded-lg">
              <Code2 className="h-4 w-4 text-cyan-400" />
              <span>Full-Stack Monorepo</span>
            </div>
            <div className="flex items-center gap-1.5 bg-slate-950/70 border border-slate-800 px-3 py-1.5 rounded-lg">
              <ShieldCheck className="h-4 w-4 text-emerald-400" />
              <span>Zip-Slip Protected</span>
            </div>
            <div className="flex items-center gap-1.5 bg-slate-950/70 border border-slate-800 px-3 py-1.5 rounded-lg">
              <GitFork className="h-4 w-4 text-indigo-400" />
              <span>Multi-Agent StateGraph</span>
            </div>
          </div>
        </div>
      </div>

      {/* Backend Status Probe */}
      <HealthCard
        health={health}
        loading={healthLoading}
        error={healthError}
        lastChecked={lastChecked}
        onRefresh={onRefresh}
      />

      {/* Phase 1: Ingestion & Storage Interface */}
      <div className="space-y-6">
        <IngestionCard onIngestionSuccess={handleIngestionSuccess} />

        {/* Ingested Repositories Section */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-1">
            <RecentRepositories
              repositories={repositories}
              activeRepoId={activeRepo?.id || null}
              onSelectRepo={handleSelectRepo}
              loading={reposLoading}
            />
          </div>

          <div className="lg:col-span-2 space-y-6">
            {activeLoading ? (
              <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-12 text-center text-slate-400">
                <p className="text-sm font-medium animate-pulse">Loading repository details & tree...</p>
              </div>
            ) : activeRepo ? (
              <>
                <RepositoryCard repository={activeRepo} />
                <CodeAnalysisSection
                  repositoryId={activeRepo.id}
                  repositoryName={activeRepo.name}
                />
                <AiFixGeneratorSection
                  repositoryId={activeRepo.id}
                  repositoryName={activeRepo.name}
                />
                <CodeSearchSection
                  repositoryId={activeRepo.id}
                  repositoryName={activeRepo.name}
                />
                <CodeIntelligenceSection
                  repositoryId={activeRepo.id}
                  repositoryName={activeRepo.name}
                />
                <DirectoryTree tree={activeRepo.tree} />
              </>
            ) : (
              <div className="bg-slate-900/40 border border-slate-800/80 rounded-2xl p-12 text-center text-slate-500">
                <FolderGit2 className="h-10 w-10 mx-auto text-slate-600 mb-2" />
                <p className="text-sm font-medium text-slate-400">No active repository selected</p>
                <p className="text-xs text-slate-500 mt-1">
                  Upload a ZIP archive or clone a GitHub repository above to explore its tree.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Development Roadmap */}
      <div>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center space-x-2">
            <Layers className="h-5 w-5 text-cyan-400" />
            <h2 className="text-lg font-bold text-slate-100">Engineering Delivery Roadmap</h2>
          </div>
          <span className="text-xs text-slate-400">Phase 5 Complete • Phase 6 Up Next</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {PHASES.map((phase) => (
            <RoadmapCard key={phase.id} phase={phase} />
          ))}
        </div>
      </div>
    </div>
  )
}
