export interface SubsystemsStatus {
  database: string
  docker_sandbox: string
  gemini_api: string
  [key: string]: string
}

export interface HealthResponse {
  status: string
  version: string
  environment: string
  timestamp: string
  subsystems: SubsystemsStatus
}

export interface RoadmapPhase {
  id: number
  title: string
  description: string
  status: 'completed' | 'in-progress' | 'planned'
  tag: string
}

export interface ApiResponse<T> {
  success: boolean
  message: string
  data: T
}

export interface LanguageDistribution {
  name: string
  file_count: number
  byte_count: number
  percentage: number
}

export interface TreeNode {
  name: string
  path: string
  type: 'file' | 'directory'
  size_bytes: number
  extension?: string | null
  language?: string | null
  children?: TreeNode[] | null
}

export interface RepositorySummary {
  id: string
  name: string
  source_type: 'ZIP' | 'GITHUB'
  remote_url?: string | null
  default_branch?: string | null
  total_files: number
  total_directories: number
  total_size_bytes: number
  languages: LanguageDistribution[]
  status: string
  created_at: string
}

export interface RepositoryDetail extends RepositorySummary {
  tree: TreeNode
}

export interface RepositoryTreeResponse {
  repository_id: string
  name: string
  tree: TreeNode
}

export * from './code_analysis'
export * from './rag'
export * from './analysis'
export * from './patch'
export * from './execution'


