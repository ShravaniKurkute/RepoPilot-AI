export interface SearchQuery {
  query: string
  top_k?: number
  search_mode?: 'hybrid' | 'semantic' | 'keyword'
  language?: string | null
  file_path?: string | null
}

export interface SearchResultChunk {
  chunk_id: string
  file_path: string
  start_line: number
  end_line: number
  language: string
  symbol_name?: string | null
  symbol_type?: string | null
  associated_class_or_function?: string | null
  content: string
  relevance_score: number
  retrieval_method: 'hybrid' | 'semantic' | 'keyword'
  semantic_score?: number | null
  keyword_score?: number | null
}

export interface SearchResponse {
  repository_id: string
  query: string
  search_mode: string
  total_results: number
  results: SearchResultChunk[]
}

export interface IndexingStatusResponse {
  repository_id: string
  status: 'idle' | 'indexing' | 'completed' | 'failed' | string
  current_stage?: string | null
  stage_message?: string | null
  total_chunks: number
  total_files_indexed: number
  new_chunks_embedded: number
  cached_chunks: number
  last_indexed_at?: string | null
  error_message?: string | null
}

export interface IndexingStatsResponse {
  repository_id: string
  total_chunks: number
  total_files: number
  total_symbols_indexed: number
  languages: Record<string, number>
  embedding_dimension: number
  embedding_model: string
  last_indexed_at?: string | null
}

