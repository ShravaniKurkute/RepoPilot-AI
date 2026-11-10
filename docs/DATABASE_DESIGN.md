# RepoPilot AI — Database Design

## 1. Overview

RepoPilot AI utilizes **PostgreSQL 16** augmented with the **pgvector** extension. This relational + vector architecture provides:
- Relational integrity for repositories, files, structural AST symbols, issue tracking, and test execution runs.
- High-performance vector similarity search (via HNSW indexing) for semantic code retrieval (RAG).
- Transactional consistency to track multi-step agent plans and multi-round self-correction history.

---

## 2. Entity-Relationship Diagram (ERD)

```mermaid
erDiagram
    REPOSITORIES ||--o{ REPOSITORY_FILES : contains
    REPOSITORIES ||--o{ ANALYSIS_SESSIONS : undergoes
    REPOSITORY_FILES ||--o{ CODE_SYMBOLS : declares
    REPOSITORY_FILES ||--o{ CODE_EMBEDDINGS : indexed_in
    CODE_SYMBOLS ||--o{ CODE_EMBEDDINGS : represents
    
    ANALYSIS_SESSIONS ||--o{ DETECTED_ISSUES : discovers
    DETECTED_ISSUES ||--o{ FIX_PLANS : resolved_by
    FIX_PLANS ||--o{ EXECUTION_RUNS : executed_in
    EXECUTION_RUNS ||--o{ TEST_RESULTS : produces

    REPOSITORIES {
        uuid id PK
        string name
        string source_type "ZIP | GITHUB"
        string remote_url
        string storage_path
        string detected_language
        timestamp created_at
        timestamp updated_at
    }

    REPOSITORY_FILES {
        uuid id PK
        uuid repository_id FK
        string relative_path
        string file_name
        string extension
        string language
        int size_bytes
        boolean is_binary
        timestamp created_at
    }

    CODE_SYMBOLS {
        uuid id PK
        uuid repository_id FK
        uuid file_id FK
        string symbol_type "class | function | method"
        string name
        string qualified_name
        int start_line
        int end_line
        text docstring
        jsonb signature
    }

    CODE_EMBEDDINGS {
        uuid id PK
        uuid repository_id FK
        uuid file_id FK
        uuid symbol_id FK
        int chunk_index
        text chunk_content
        vector embedding "vector(768)"
        timestamp created_at
    }

    ANALYSIS_SESSIONS {
        uuid id PK
        uuid repository_id FK
        string status "PENDING | ANALYZING | COMPLETED | FAILED"
        int total_issues
        jsonb summary_metrics
        timestamp created_at
        timestamp completed_at
    }

    DETECTED_ISSUES {
        uuid id PK
        uuid session_id FK
        uuid file_id FK
        string issue_type "BUG | SECURITY | CODE_SMELL | PERFORMANCE"
        string severity "CRITICAL | HIGH | MEDIUM | LOW"
        string title
        text description
        int line_number
        text code_snippet
        text remediation_hint
    }

    FIX_PLANS {
        uuid id PK
        uuid session_id FK
        uuid issue_id FK
        string status "DRAFT | EXECUTING | VERIFIED | FAILED"
        jsonb plan_steps
        jsonb target_files
        text generated_patch
        int retry_count
        timestamp created_at
    }

    EXECUTION_RUNS {
        uuid id PK
        uuid fix_plan_id FK
        string container_id
        string status "RUNNING | SUCCESS | FAILED | TIMEOUT"
        int exit_code
        text stdout
        text stderr
        float execution_time_seconds
        timestamp created_at
    }

    TEST_RESULTS {
        uuid id PK
        uuid execution_run_id FK
        string test_name
        string status "PASSED | FAILED | ERROR | SKIPPED"
        float duration_ms
        text failure_message
        text stack_trace
    }
```

---

## 3. Schema DDL & Specification

### 3.1 Extension Activation
```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";
```

### 3.2 Repositories & File Hierarchy
```sql
CREATE TABLE repositories (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    source_type VARCHAR(50) NOT NULL, -- 'ZIP' or 'GITHUB'
    remote_url VARCHAR(1024),
    storage_path VARCHAR(1024) NOT NULL,
    detected_language VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE repository_files (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    relative_path VARCHAR(1024) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    extension VARCHAR(50),
    language VARCHAR(50),
    size_bytes INTEGER NOT NULL,
    is_binary BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    CONSTRAINT uq_repo_path UNIQUE (repository_id, relative_path)
);
```

### 3.3 Syntactic Intelligence & Embeddings (pgvector)
```sql
CREATE TABLE code_symbols (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    file_id UUID NOT NULL REFERENCES repository_files(id) ON DELETE CASCADE,
    symbol_type VARCHAR(50) NOT NULL, -- 'class', 'function', 'method'
    name VARCHAR(255) NOT NULL,
    qualified_name VARCHAR(512),
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    docstring TEXT,
    signature JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE code_embeddings (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    file_id UUID NOT NULL REFERENCES repository_files(id) ON DELETE CASCADE,
    symbol_id UUID REFERENCES code_symbols(id) ON DELETE SET NULL,
    chunk_index INTEGER NOT NULL,
    chunk_content TEXT NOT NULL,
    embedding VECTOR(768), -- Google Gemini Text Embedding 004 dimension
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Fast cosine similarity search with HNSW Index
CREATE INDEX idx_code_embeddings_hnsw 
ON code_embeddings 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

### 3.4 Analysis Sessions & Issues
```sql
CREATE TABLE analysis_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    repository_id UUID NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    total_issues INTEGER DEFAULT 0,
    summary_metrics JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE TABLE detected_issues (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES analysis_sessions(id) ON DELETE CASCADE,
    file_id UUID REFERENCES repository_files(id) ON DELETE SET NULL,
    issue_type VARCHAR(50) NOT NULL, -- 'BUG', 'SECURITY', 'CODE_SMELL', 'PERFORMANCE'
    severity VARCHAR(20) NOT NULL,   -- 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'
    title VARCHAR(500) NOT NULL,
    description TEXT NOT NULL,
    line_number INTEGER,
    code_snippet TEXT,
    remediation_hint TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 3.5 Fix Plans, Execution & Validation
```sql
CREATE TABLE fix_plans (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id UUID NOT NULL REFERENCES analysis_sessions(id) ON DELETE CASCADE,
    issue_id UUID REFERENCES detected_issues(id) ON DELETE SET NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'DRAFT',
    plan_steps JSONB NOT NULL,
    target_files JSONB NOT NULL,
    generated_patch TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE execution_runs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fix_plan_id UUID NOT NULL REFERENCES fix_plans(id) ON DELETE CASCADE,
    container_id VARCHAR(128),
    status VARCHAR(50) NOT NULL, -- 'RUNNING', 'SUCCESS', 'FAILED', 'TIMEOUT'
    exit_code INTEGER,
    stdout TEXT,
    stderr TEXT,
    execution_time_seconds FLOAT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE test_results (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    execution_run_id UUID NOT NULL REFERENCES execution_runs(id) ON DELETE CASCADE,
    test_name VARCHAR(512) NOT NULL,
    status VARCHAR(50) NOT NULL, -- 'PASSED', 'FAILED', 'ERROR', 'SKIPPED'
    duration_ms FLOAT,
    failure_message TEXT,
    stack_trace TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

