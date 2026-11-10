"""Context Enrichment Node: retrieves AST structural relations, dependencies, and RAG context."""

from pathlib import Path
from typing import Any, Dict, List, Optional

from app.code_analysis.service import code_analysis_service
from app.core.config import settings
from app.patch.state import AgentWorkflowState
from app.rag.schemas import SearchQuery
from app.rag.service import rag_service


async def enrich_context_node(state: AgentWorkflowState) -> Dict[str, Any]:
    """Retrieves function definitions, callers, callees, imports, RAG chunks, and related tests."""
    repo_id = state["repository_id"]
    rel_path = state.get("target_file_path") or ""
    issue_data = state.get("issue_data") or {}
    affected_symbol_name = issue_data.get("affected_symbol") or ""

    # 1. AST Analysis Lookup
    ast_analysis = code_analysis_service.get_analysis(repo_id)
    file_ast = ast_analysis.files.get(rel_path) if ast_analysis else None

    affected_symbol_info = None
    callers: List[str] = []
    callees: List[str] = []
    declared_imports: List[str] = []

    if file_ast:
        # Find affected symbol
        for sym in file_ast.symbols:
            if sym.name == affected_symbol_name or affected_symbol_name in sym.name:
                affected_symbol_info = sym.model_dump()
                break

        # Collect callers from call graph
        if ast_analysis and ast_analysis.call_graph:
            # ast_analysis.call_graph is a List[CallGraphEdge]
            call_graph_items = (
                ast_analysis.call_graph
                if isinstance(ast_analysis.call_graph, list)
                else getattr(ast_analysis.call_graph, "edges", [])
            )
            for edge in call_graph_items:
                callee = getattr(edge, "callee_name", None)
                caller = getattr(edge, "caller_name", None)
                if callee and callee == affected_symbol_name and caller:
                    callers.append(caller)
                elif caller and caller == affected_symbol_name and callee:
                    callees.append(callee)

        # Collect unique imports
        declared_imports = [imp.statement.strip() for imp in file_ast.imports[:10]]

    # 2. Related Test Files Identification
    from app.repository.service import repository_service
    storage_root = repository_service.storage_root
    source_dir = storage_root / repo_id / "source"
    if not source_dir.exists():
        source_dir = storage_root / repo_id

    related_tests: List[str] = []
    try:
        base_name = rel_path.split("/")[-1].split(".")[0]
        for candidate in source_dir.glob("**/test_*.py"):
            rel_cand = candidate.relative_to(source_dir).as_posix()
            if base_name in rel_cand or "test" in rel_cand:
                related_tests.append(rel_cand)
                if len(related_tests) >= 3:
                    break
    except Exception:
        pass

    # 3. RAG Context Retrieval
    rag_snippets: List[Dict[str, str]] = []
    try:
        search_query = f"{affected_symbol_name or rel_path} callers error handling"
        search_res = await rag_service.search(
            repository_id=repo_id,
            search_query=SearchQuery(
                query=search_query,
                top_k=3,
                search_mode="hybrid",
            ),
        )
        for chunk in search_res.results:
            if chunk.file_path != rel_path:
                rag_snippets.append(
                    {
                        "file_path": chunk.file_path,
                        "lines": f"{chunk.start_line}-{chunk.end_line}",
                        "content": chunk.content[:400].strip(),
                    }
                )
    except Exception:
        pass

    enriched = {
        "affected_symbol": affected_symbol_info,
        "callers": list(set(callers))[:8],
        "callees": list(set(callees))[:8],
        "imports": declared_imports,
        "related_tests": related_tests,
        "rag_snippets": rag_snippets,
    }

    return {
        "retrieved_context": enriched,
        "workflow_status": "planning_fix",
    }
