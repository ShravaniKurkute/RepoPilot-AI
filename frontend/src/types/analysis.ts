export type IssueSeverity = 'Critical' | 'High' | 'Medium' | 'Low' | 'Informational'
export type IssueCategory = 'logic_bug' | 'security_vulnerability' | 'code_smell'
export type IssueStatus = 'Open' | 'Confirmed' | 'False Positive' | 'Resolved' | 'Ignored'

export interface CodeIssue {
  issue_id: string
  repository_id: string
  analysis_run_id: string
  file_path: string
  language: string
  issue_title: string
  issue_description: string
  category: IssueCategory
  subcategory?: string | null
  severity: IssueSeverity
  confidence_score: number
  start_line: number
  end_line: number
  affected_symbol?: string | null
  evidence: string
  technical_explanation: string
  potential_impact: string
  suggested_fix: string
  related_files: string[]
  cwe_id?: string | null
  detection_method: string
  status: IssueStatus
  created_at: string
}

export interface AnalysisRun {
  run_id: string
  repository_id: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'timed_out'
  current_stage?: string | null
  stage_message?: string | null
  target_type: 'repository' | 'file' | 'symbol'
  target_path?: string | null
  total_files: number
  analyzed_files: number
  total_issues: number
  critical_count: number
  high_count: number
  medium_count: number
  low_count: number
  informational_count: number
  started_at: string
  completed_at?: string | null
  error_message?: string | null
}

export interface AnalyzeFileRequest {
  file_path: string
  categories?: IssueCategory[] | null
}

export interface AnalyzeFunctionRequest {
  file_path: string
  symbol_name: string
}

export interface UpdateIssueStatusRequest {
  status: IssueStatus
  notes?: string | null
}

export interface IssueListResponse {
  repository_id: string
  total_issues: number
  severity_breakdown: Record<string, number>
  category_breakdown: Record<string, number>
  issues: CodeIssue[]
}

export interface AnalysisRunStatusResponse {
  run: AnalysisRun
  recent_issues: CodeIssue[]
}

