export interface SourceLocation {
  start_line: number
  end_line: number
  start_column: number
  end_column: number
}

export interface Symbol {
  id: string
  name: string
  symbol_type: string
  file_path: string
  location: SourceLocation
  parent_symbol_id?: string | null
  language: string
  parameters?: string[]
  return_type?: string | null
  decorators?: string[]
  visibility?: 'public' | 'private' | 'protected' | string | null
  docstring?: string | null
  is_async: boolean
}

export interface ImportStatement {
  source_file: string
  statement: string
  module: string
  names: string[]
  aliases: Record<string, string>
  is_relative: boolean
  resolved_target_file?: string | null
  import_type: 'local' | 'external' | 'unresolved' | string
  line_number: number
}

export interface CallGraphEdge {
  id: string
  caller_id: string
  caller_name: string
  caller_file: string
  callee_name: string
  resolved_callee_id?: string | null
  resolved_callee_file?: string | null
  is_resolved: boolean
  line_number: number
}

export interface FileAnalysisResult {
  file_path: string
  language: string
  status: 'success' | 'syntax_error' | 'unsupported' | string
  error_message?: string | null
  symbols: Symbol[]
  imports: ImportStatement[]
  function_calls: CallGraphEdge[]
  total_lines: number
}

export interface FileDependency {
  file_path: string
  depends_on: string[]
  imported_by: string[]
  external_dependencies: string[]
  unresolved_imports: string[]
}

export interface RepositoryAnalysisSummary {
  repository_id: string
  total_files_scanned: number
  successfully_parsed_files: number
  failed_files: number
  unsupported_files: number
  total_symbols: number
  total_functions: number
  total_classes: number
  total_imports: number
  total_call_edges: number
  resolved_call_edges: number
  has_circular_dependencies: boolean
  circular_dependency_cycles: string[][]
  languages_analyzed: string[]
  analyzed_at: string
}

export interface RepositoryAnalysisResponse {
  summary: RepositoryAnalysisSummary
  symbols: Symbol[]
  dependencies: Record<string, FileDependency>
  call_graph: CallGraphEdge[]
  files: Record<string, FileAnalysisResult>
}

