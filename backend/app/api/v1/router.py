"""Master router aggregating all v1 API endpoints."""

from fastapi import APIRouter
from app.api.v1.analysis import router as analysis_router
from app.api.v1.code_analysis import router as code_analysis_router
from app.api.v1.execution import router as execution_router
from app.api.v1.health import router as health_router
from app.api.v1.patches import router as patches_router
from app.api.v1.rag import router as rag_router
from app.api.v1.repositories import router as repositories_router

api_v1_router = APIRouter()

# Mount health routes
api_v1_router.include_router(health_router, prefix="", tags=["Health"])

# Phase 1: Repository Ingestion & Storage routes
api_v1_router.include_router(repositories_router, prefix="", tags=["Repositories"])

# Phase 2: Code Intelligence & AST Parsing routes
api_v1_router.include_router(code_analysis_router, prefix="", tags=["Code Intelligence"])

# Phase 3: Repository-Aware RAG & Hybrid Code Retrieval
api_v1_router.include_router(rag_router, prefix="", tags=["Code RAG & Search"])

# Phase 4: AI-Powered Code Analysis & Bug Detection
api_v1_router.include_router(analysis_router, prefix="", tags=["AI Code Analysis"])

# Phase 5: Agentic Planning & Patch Generation
api_v1_router.include_router(patches_router, prefix="", tags=["Phase 5: Agentic Planning & Patch Generation"])

# Phase 6: Docker Sandbox Execution Engine
api_v1_router.include_router(execution_router, prefix="", tags=["Phase 6: Docker Sandbox Execution Engine"])

