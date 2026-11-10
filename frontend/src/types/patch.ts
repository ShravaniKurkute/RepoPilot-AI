export type RiskLevel = 'Low' | 'Medium' | 'High' | 'Critical'
export type ValidationStatus = 'valid' | 'invalid' | 'rejected'
export type ReviewStatus = 'pending_review' | 'approved' | 'rejected'
export type ReviewDecision = 'approved' | 'rejected' | 'regeneration_requested'

export interface FixPlan {
  id: string
  issue_id: string
  repository_id: string
  summary: string
  root_cause: string
  proposed_solution: string
  implementation_steps: string[]
  affected_files: string[]
  impact_report: Record<string, any>
  risk_level: RiskLevel
  expected_behavior: string
  recommended_tests: string[]
  created_at: string
}

export interface PatchProposal {
  id: string
  repository_id: string
  issue_id: string
  fix_plan_id: string
  patch_content: string
  affected_files: string[]
  original_snippets: Record<string, string>
  modified_snippets: Record<string, string>
  lines_added: number
  lines_removed: number
  confidence_score: number
  risk_level: RiskLevel
  validation_status: ValidationStatus
  validation_details: Record<string, any>
  review_status: ReviewStatus
  workflow_status: string
  regeneration_attempt: number
  created_at: string
  updated_at: string
}

export interface PatchReviewRequest {
  decision: ReviewDecision
  reviewer_feedback?: string | null
}

export interface RegeneratePatchRequest {
  feedback?: string | null
}

export interface PatchProposalListResponse {
  repository_id: string
  total_patches: number
  patches: PatchProposal[]
}

export interface WorkflowStatusResponse {
  patch_id?: string | null
  repository_id: string
  issue_id: string
  status: string
  review_status?: string | null
  validation_status?: string | null
  risk_level?: string | null
  lines_added: number
  lines_removed: number
  current_step?: string | null
  regeneration_attempt: number
  error_details?: string | null
}

