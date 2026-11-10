"""Comprehensive unit and integration tests for Phase 4: AI-Powered Code Analysis & Bug Detection."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from app.analysis.analyzer import GeminiCodeAnalyzer, MockCodeAnalyzer
from app.analysis.confidence import ConfidenceValidator
from app.analysis.context_builder import AnalysisContext, AnalysisContextBuilder
from app.analysis.issue_classifier import IssueClassifier
from app.analysis.schemas import CodeIssue
from app.analysis.service import BugDetectionService
from app.code_analysis.schemas import FileAnalysisResult, SourceLocation, Symbol
from app.main import app

client = TestClient(app)


# -------------------------------------------------------------
# 1. Logic Bug, Security Vulnerability & Code Smell Detection
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_logic_bug_detection():
    analyzer = MockCodeAnalyzer()
    bad_code = """def compute_ratio(total, count):
    if count is None: count.reset()
    ratio = total / 0
    return ratio
"""
    context = AnalysisContext(
        repository_id="test-repo",
        file_path="math_utils.py",
        language="Python",
        target_code=bad_code,
        start_line=1,
        end_line=5,
        symbol_name="compute_ratio",
    )

    findings = await analyzer.analyze_context(context)
    assert len(findings) >= 2

    # Check division by zero finding
    div_zero = next((f for f in findings if f["subcategory"] == "division_by_zero"), None)
    assert div_zero is not None
    assert div_zero["category"] == "logic_bug"
    assert div_zero["severity"] == "High"
    assert "total / 0" in div_zero["evidence"]
    assert div_zero["cwe_id"] == "CWE-369"


@pytest.mark.asyncio
async def test_security_vulnerability_detection():
    analyzer = MockCodeAnalyzer()
    vuln_code = """import os
api_key = "sk_live_1234567890abcdef"

def fetch_record(user_id, file_name):
    query = f"SELECT * FROM users WHERE id = '{user_id}'"
    f = open(file_name, "r")
    return query
"""
    context = AnalysisContext(
        repository_id="test-repo",
        file_path="db_service.py",
        language="Python",
        target_code=vuln_code,
        start_line=1,
        end_line=8,
        symbol_name="fetch_record",
    )

    findings = await analyzer.analyze_context(context)
    subcategories = [f["subcategory"] for f in findings]

    assert "sql_injection" in subcategories
    assert "path_traversal" in subcategories
    assert "hardcoded_credentials" in subcategories

    sqli = next(f for f in findings if f["subcategory"] == "sql_injection")
    assert sqli["category"] == "security_vulnerability"
    assert sqli["severity"] == "Critical"
    assert sqli["cwe_id"] == "CWE-89"


@pytest.mark.asyncio
async def test_code_smell_detection():
    analyzer = MockCodeAnalyzer()
    nested_code = """def evaluate_data(a, b, c, d):
    if a:
        if b:
            if c:
                if d:
                    return True
    return False
"""
    context = AnalysisContext(
        repository_id="test-repo",
        file_path="complex.py",
        language="Python",
        target_code=nested_code,
        start_line=1,
        end_line=8,
        symbol_name="evaluate_data",
    )

    findings = await analyzer.analyze_context(context)
    smell = next((f for f in findings if f["category"] == "code_smell"), None)
    assert smell is not None
    assert smell["subcategory"] == "cognitive_complexity"
    assert smell["severity"] == "Low"


@pytest.mark.asyncio
async def test_negative_clean_code_no_false_positives():
    analyzer = MockCodeAnalyzer()
    clean_code = """def safe_divide(a: float, b: float) -> float:
    if b == 0:
        raise ValueError("Cannot divide by zero")
    return a / b

def get_user_by_id(db_session, user_id: int):
    # Parameterized query with bound parameters
    return db_session.execute(select(User).where(User.id == user_id)).scalar_one_or_none()
"""
    context = AnalysisContext(
        repository_id="test-repo",
        file_path="clean.py",
        language="Python",
        target_code=clean_code,
        start_line=1,
        end_line=9,
        symbol_name="safe_divide",
    )

    findings = await analyzer.analyze_context(context)
    # Clean code should not report false positive SQLi or div zero
    assert len(findings) == 0


# -------------------------------------------------------------
# 2. Context Builder & Confidence Validator Tests
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_context_builder():
    builder = AnalysisContextBuilder(max_rag_chunks=3)
    source = """class DataProcessor:
    def process(self, data):
        return data.strip()
"""
    symbol = Symbol(
        id="proc.py::process::2",
        name="process",
        symbol_type="method",
        file_path="proc.py",
        location=SourceLocation(start_line=2, end_line=3, start_column=5, end_column=28),
        parent_symbol_id="proc.py::DataProcessor::1::class",
        language="Python",
        parameters=["self", "data"],
    )
    analysis = FileAnalysisResult(
        file_path="proc.py",
        language="Python",
        status="success",
        symbols=[symbol],
        imports=[],
        function_calls=[],
        total_lines=3,
    )

    ctx = await builder.build_context_for_symbol(
        repository_id="test-repo",
        file_path="proc.py",
        source_code=source,
        symbol=symbol,
        file_analysis=analysis,
    )

    assert ctx.start_line == 2
    assert ctx.end_line == 3
    assert "return data.strip()" in ctx.target_code
    assert "Parameters: (self, data)" in ctx.ast_summary


def test_confidence_validator_and_deduplication():
    validator = ConfidenceValidator(min_confidence=0.5)
    source = "line 1\nline 2\nline 3\n"

    issue1 = CodeIssue(
        issue_id="issue1",
        repository_id="repo1",
        analysis_run_id="run1",
        file_path="test.py",
        language="Python",
        issue_title="Bug Title",
        issue_description="Desc",
        category="logic_bug",
        severity="High",
        confidence_score=0.9,
        start_line=1,
        end_line=2,
        evidence="line 1\nline 2",
        technical_explanation="Expl",
        potential_impact="Impact",
        suggested_fix="Fix",
    )

    # Identical issue with lower confidence (should be deduplicated)
    issue2 = issue1.model_copy(update={"issue_id": "issue2", "confidence_score": 0.7})

    # Issue with low confidence < 0.5 (should be dropped)
    issue_low = issue1.model_copy(update={"issue_id": "issue_low", "confidence_score": 0.3})

    filtered = validator.validate_and_filter([issue1, issue2, issue_low], source)
    assert len(filtered) == 1
    assert filtered[0].confidence_score == 0.9


# -------------------------------------------------------------
# 3. BugDetectionService & REST API Integration
# -------------------------------------------------------------
@pytest.mark.asyncio
async def test_analysis_service_and_endpoints(tmp_path: Path):
    repo_id = "test-repo-ai-analysis"
    repo_dir = tmp_path / repo_id
    source_dir = repo_dir / "source"
    source_dir.mkdir(parents=True)

    # Write vulnerable code file
    (source_dir / "user_service.py").write_text(
        """def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = '{user_id}'"
    return query
""",
        encoding="utf-8",
    )

    service = BugDetectionService(
        analyzer=MockCodeAnalyzer(),
        storage_root=tmp_path,
    )

    # 1. Run repository analysis
    run = await service.analyze_repository(repo_id)
    assert run.status == "completed"
    assert run.total_files == 1
    assert run.total_issues >= 1
    assert run.critical_count >= 1

    # 2. Query issues
    issues_resp = service.get_issues(repo_id)
    assert issues_resp.total_issues >= 1
    found_issue = issues_resp.issues[0]
    assert found_issue.category == "security_vulnerability"
    assert found_issue.cwe_id == "CWE-89"
    assert found_issue.status == "Open"

    # 3. Update issue status
    updated = await service.update_issue_status(
        issue_id=found_issue.issue_id,
        new_status="Confirmed",
    )
    assert updated is not None
    assert updated.status == "Confirmed"

    # Wire into FastAPI router
    from app.api.v1 import analysis
    orig_service = analysis.bug_detection_service
    analysis.bug_detection_service = service

    try:
        # Trigger analyze endpoint
        post_resp = client.post(f"/api/v1/repositories/{repo_id}/ai-analyze")
        assert post_resp.status_code == 200
        run_data = post_resp.json()["data"]
        assert run_data["total_issues"] >= 1

        # File analyze endpoint
        file_resp = client.post(
            f"/api/v1/repositories/{repo_id}/ai-analyze/file",
            json={"file_path": "user_service.py"},
        )
        assert file_resp.status_code == 200

        # Status endpoint
        status_resp = client.get(f"/api/v1/repositories/{repo_id}/ai-analysis/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["data"]["status"] == "completed"

        # Issues endpoint with filters
        issues_get = client.get(
            f"/api/v1/repositories/{repo_id}/issues?severity=Critical&category=security_vulnerability"
        )
        assert issues_get.status_code == 200
        data = issues_get.json()["data"]
        assert data["total_issues"] >= 1

        # Single issue detail endpoint
        issue_id = found_issue.issue_id
        detail_get = client.get(f"/api/v1/repositories/{repo_id}/issues/{issue_id}")
        assert detail_get.status_code == 200
        assert detail_get.json()["data"]["issue_id"] == issue_id

        # Update status PATCH endpoint
        patch_resp = client.patch(
            f"/api/v1/issues/{issue_id}/status",
            json={"status": "Resolved", "notes": "Patched with parameterized query"},
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["data"]["status"] == "Resolved"

    finally:
        analysis.bug_detection_service = orig_service


# -------------------------------------------------------------
# 4. GeminiCodeAnalyzer Interactions API & SDK Unit Tests
# -------------------------------------------------------------
def test_gemini_analyzer_initialization_and_model_normalization():
    """Verify GeminiCodeAnalyzer handles model names with or without models/ prefix."""
    analyzer1 = GeminiCodeAnalyzer(api_key="AIzaSyTest123", model_name="gemini-3.8-flash")
    assert analyzer1._normalize_model() == "gemini-3.8-flash"
    assert analyzer1.provider_name == "gemini (gemini-3.8-flash)"

    analyzer2 = GeminiCodeAnalyzer(api_key="AIzaSyTest123", model_name="models/gemini-3.8-flash")
    assert analyzer2._normalize_model() == "gemini-3.8-flash"
    assert analyzer2.provider_name == "gemini (gemini-3.8-flash)"


@pytest.mark.asyncio
async def test_gemini_analyzer_interactions_api_success():
    """Verify GeminiCodeAnalyzer successfully queries Interactions API and parses structured findings."""
    analyzer = GeminiCodeAnalyzer(api_key="AIzaSyTestKey123", model_name="gemini-3.8-flash")

    sample_finding = [
        {
            "issue_title": "Potential Null Pointer Dereference",
            "issue_description": "Variable dereferenced without None check",
            "category": "logic_bug",
            "subcategory": "null_pointer",
            "severity": "High",
            "confidence_score": 0.85,
            "start_line": 10,
            "end_line": 12,
            "evidence": "data.process()",
            "technical_explanation": "data could be None if fetch fails",
            "potential_impact": "Application crash with AttributeError",
            "suggested_fix": "if data is not None: data.process()",
        }
    ]

    mock_interaction = MagicMock()
    mock_interaction.output_text = '```json\n' + json.dumps(sample_finding) + '\n```'

    mock_client = MagicMock()
    mock_client.aio = MagicMock()
    mock_client.aio.interactions = MagicMock()
    mock_client.aio.interactions.create = AsyncMock(return_value=mock_interaction)

    context = AnalysisContext(
        repository_id="test-repo",
        file_path="service.py",
        language="Python",
        target_code="def run(data):\n    data.process()\n",
        start_line=10,
        end_line=12,
        symbol_name="run",
    )

    with patch.object(analyzer, "_get_client", return_value=mock_client):
        findings = await analyzer.analyze_context(context)

    assert len(findings) == 1
    assert findings[0]["issue_title"] == "Potential Null Pointer Dereference"
    assert findings[0]["category"] == "logic_bug"
    assert findings[0]["severity"] == "High"

    mock_client.aio.interactions.create.assert_awaited_once()
    call_kwargs = mock_client.aio.interactions.create.call_args.kwargs
    assert call_kwargs["model"] == "gemini-3.8-flash"
    assert call_kwargs["response_format"] == {"type": "text", "mime_type": "application/json"}
    assert call_kwargs["generation_config"] == {"thinking_level": "low"}


@pytest.mark.asyncio
async def test_gemini_analyzer_fallback_to_generate_content():
    """Verify GeminiCodeAnalyzer gracefully falls back to SDK generate_content when Interactions API reports route issues."""
    analyzer = GeminiCodeAnalyzer(api_key="AIzaSyTestKey123", model_name="gemini-3.8-flash", max_retries=1)

    sample_finding = [
        {
            "issue_title": "SQL Injection",
            "category": "security_vulnerability",
            "severity": "Critical",
            "confidence_score": 0.95,
            "start_line": 5,
            "end_line": 6,
            "evidence": "SELECT * FROM users",
            "technical_explanation": "Direct formatting",
            "potential_impact": "Data leak",
            "suggested_fix": "Use params",
        }
    ]

    mock_gen_response = MagicMock()
    mock_gen_response.text = json.dumps(sample_finding)

    mock_client = MagicMock()
    mock_client.aio = MagicMock()
    mock_client.aio.interactions = MagicMock()
    mock_client.aio.interactions.create = AsyncMock(side_effect=Exception("HTTP 404: Interactions endpoint not supported"))
    mock_client.aio.models = MagicMock()
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_gen_response)

    context = AnalysisContext(
        repository_id="test-repo",
        file_path="db.py",
        language="Python",
        target_code="query = f'SELECT * FROM users WHERE id = {uid}'",
        start_line=5,
        end_line=6,
    )

    with patch.object(analyzer, "_get_client", return_value=mock_client):
        findings = await analyzer.analyze_context(context)

    assert len(findings) == 1
    assert findings[0]["issue_title"] == "SQL Injection"
    mock_client.aio.models.generate_content.assert_awaited_once()


@pytest.mark.asyncio
async def test_gemini_analyzer_error_handling_and_redaction():
    """Verify specific HTTP error handling (401, 404, 503, timeout) and key redaction."""
    test_key = "AIzaSySecretApiKeyToRedact999"
    analyzer = GeminiCodeAnalyzer(api_key=test_key, max_retries=1, timeout=10.0)

    context = AnalysisContext(
        repository_id="test-repo",
        file_path="main.py",
        language="Python",
        target_code="pass",
        start_line=1,
        end_line=1,
    )

    # 1. Redaction method test
    leaked_msg = f"Failed with {test_key} at endpoint"
    sanitized = analyzer._sanitize_error(leaked_msg)
    assert test_key not in sanitized
    assert "[REDACTED_API_KEY]" in sanitized

    # 2. 401 Unauthorized
    mock_client_401 = MagicMock()
    mock_client_401.aio.interactions.create = AsyncMock(
        side_effect=Exception(f"401 API_KEY_INVALID: Key {test_key} not valid")
    )
    with patch.object(analyzer, "_get_client", return_value=mock_client_401):
        with pytest.raises(RuntimeError) as exc_401:
            await analyzer.analyze_context(context)
        err_text = str(exc_401.value)
        assert "401 Unauthorized" in err_text
        assert test_key not in err_text

    # 3. 404 Model Not Found
    mock_client_404 = MagicMock()
    mock_client_404.aio.interactions.create = AsyncMock(
        side_effect=Exception("404 Model models/gemini-2.5-flash is no longer available")
    )
    mock_client_404.aio.models.generate_content = AsyncMock(
        side_effect=Exception("404 Model models/gemini-2.5-flash is no longer available")
    )
    with patch.object(analyzer, "_get_client", return_value=mock_client_404):
        with pytest.raises(RuntimeError) as exc_404:
            await analyzer.analyze_context(context)
        assert "404 Not Found" in str(exc_404.value)

    # 4. 503 High Demand
    mock_client_503 = MagicMock()
    mock_client_503.aio.interactions.create = AsyncMock(
        side_effect=Exception("503 This model is currently experiencing high demand")
    )
    with patch.object(analyzer, "_get_client", return_value=mock_client_503):
        with pytest.raises(RuntimeError) as exc_503:
            await analyzer.analyze_context(context)
        assert "503" in str(exc_503.value) or "high demand" in str(exc_503.value)

    # 5. Timeout
    mock_client_timeout = MagicMock()
    mock_client_timeout.aio.interactions.create = AsyncMock(
        side_effect=Exception("Client timeout while waiting for response")
    )
    with patch.object(analyzer, "_get_client", return_value=mock_client_timeout):
        with pytest.raises(RuntimeError) as exc_timeout:
            await analyzer.analyze_context(context)
        assert "timed out" in str(exc_timeout.value).lower()


def test_gemini_analyzer_safe_parse_json_variants():
    """Verify _safe_parse_json handles markdown formatting, dictionaries, arrays, and invalid text."""
    analyzer = GeminiCodeAnalyzer(api_key="AIzaSyTestKey")

    # 1. Plain array
    res1 = analyzer._safe_parse_json('[{"issue_title": "Issue 1"}]')
    assert len(res1) == 1 and res1[0]["issue_title"] == "Issue 1"

    # 2. Markdown fenced array
    res2 = analyzer._safe_parse_json('```json\n[{"issue_title": "Issue 2"}]\n```')
    assert len(res2) == 1 and res2[0]["issue_title"] == "Issue 2"

    # 3. Object with issues key
    res3 = analyzer._safe_parse_json('{"issues": [{"issue_title": "Issue 3"}]}')
    assert len(res3) == 1 and res3[0]["issue_title"] == "Issue 3"

    # 4. Markdown fenced object
    res4 = analyzer._safe_parse_json('```\n{"issues": [{"issue_title": "Issue 4"}]}\n```')
    assert len(res4) == 1 and res4[0]["issue_title"] == "Issue 4"

    # 5. Text with conversational preamble
    res5 = analyzer._safe_parse_json('Here are the discovered bugs:\n[{"issue_title": "Issue 5"}]\nPlease fix them.')
    assert len(res5) == 1 and res5[0]["issue_title"] == "Issue 5"

    # 6. Invalid text / empty string
    assert analyzer._safe_parse_json("") == []
    assert analyzer._safe_parse_json("Not a valid json response") == []


# -------------------------------------------------------------
# 5. Timeout Handling, Context Optimization & Retry Tests
# -------------------------------------------------------------
def test_gemini_analyzer_timeout_and_transport_configuration():
    """Verify GeminiCodeAnalyzer sets 180s default timeout and configures transport-level HttpOptions."""
    from app.core.config import settings

    analyzer = GeminiCodeAnalyzer(api_key="AIzaSyTest123")
    assert analyzer._timeout == 180.0
    assert analyzer._max_retries == settings.ANALYSIS_MAX_RETRIES

    with patch("google.genai.Client") as mock_client_cls:
        client_instance = analyzer._get_client()
        mock_client_cls.assert_called_once()
        call_kwargs = mock_client_cls.call_args.kwargs
        assert call_kwargs["api_key"] == "AIzaSyTest123"
        assert "http_options" in call_kwargs
        assert call_kwargs["http_options"].timeout == 180000


@pytest.mark.asyncio
async def test_delayed_gemini_response_within_timeout():
    """Verify GeminiCodeAnalyzer processes responses that take time without premature timeout."""
    analyzer = GeminiCodeAnalyzer(api_key="AIzaSyTestKey123", timeout=180.0)

    sample_finding = [
        {
            "issue_title": "Division by Zero",
            "category": "logic_bug",
            "severity": "High",
            "confidence_score": 0.9,
            "start_line": 2,
            "end_line": 2,
            "evidence": "a / 0",
            "technical_explanation": "Zero denominator",
            "potential_impact": "Crash",
            "suggested_fix": "Guard against zero",
        }
    ]

    mock_interaction = MagicMock()
    mock_interaction.output_text = json.dumps(sample_finding)

    async def _delayed_create(*args, **kwargs):
        await asyncio.sleep(0.05)  # Simulate network and reasoning latency
        return mock_interaction

    mock_client = MagicMock()
    mock_client.aio = MagicMock()
    mock_client.aio.interactions = MagicMock()
    mock_client.aio.interactions.create = AsyncMock(side_effect=_delayed_create)

    context = AnalysisContext(
        repository_id="test-repo",
        file_path="math.py",
        language="Python",
        target_code="x = a / 0",
        start_line=2,
        end_line=2,
    )

    with patch.object(analyzer, "_get_client", return_value=mock_client):
        findings = await analyzer.analyze_context(context)

    assert len(findings) == 1
    assert findings[0]["issue_title"] == "Division by Zero"


@pytest.mark.asyncio
async def test_gemini_analyzer_client_side_timeout_exception():
    """Verify client-side timeout raises descriptive RuntimeError with configured timeout value."""
    analyzer = GeminiCodeAnalyzer(api_key="AIzaSyTestKey123", timeout=180.0, max_retries=1)

    mock_client = MagicMock()
    mock_client.aio = MagicMock()
    mock_client.aio.interactions = MagicMock()
    mock_client.aio.interactions.create = AsyncMock(
        side_effect=Exception("Request timed out. This is a client-side timeout.")
    )

    context = AnalysisContext(
        repository_id="test-repo",
        file_path="main.py",
        language="Python",
        target_code="pass",
        start_line=1,
        end_line=1,
    )

    with patch.object(analyzer, "_get_client", return_value=mock_client):
        with pytest.raises(RuntimeError) as exc_info:
            await analyzer.analyze_context(context)

        err_msg = str(exc_info.value)
        assert "timed out after 180.0s" in err_msg
        assert "client-side timeout" in err_msg


def test_retry_after_extraction_and_permanent_error_discrimination():
    """Verify retry delay parsing from Retry-After headers/messages and permanent error discrimination."""
    analyzer = GeminiCodeAnalyzer(api_key="AIzaSyKey")

    # 1. Retry-After regex extraction
    e1 = Exception("429 RESOURCE_EXHAUSTED: Rate limit exceeded. Retry-After: 12.5 seconds")
    assert analyzer._extract_retry_after(e1) == 12.5

    e2 = Exception("Service unavailable. Try again in 5 seconds")
    assert analyzer._extract_retry_after(e2) == 5.0

    e3 = Exception("Plain error without retry hint")
    assert analyzer._extract_retry_after(e3) is None


@pytest.mark.asyncio
async def test_permanent_error_fails_immediately_without_retries():
    """Verify permanent errors (401, 404) immediately fail and do not waste retries."""
    analyzer = GeminiCodeAnalyzer(api_key="AIzaSyKey", max_retries=3)

    call_count = 0

    async def _failing_create(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        raise Exception("401 API_KEY_INVALID: Key not authorized")

    mock_client = MagicMock()
    mock_client.aio = MagicMock()
    mock_client.aio.interactions = MagicMock()
    mock_client.aio.interactions.create = AsyncMock(side_effect=_failing_create)

    context = AnalysisContext(
        repository_id="test-repo",
        file_path="main.py",
        language="Python",
        target_code="pass",
        start_line=1,
        end_line=1,
    )

    with patch.object(analyzer, "_get_client", return_value=mock_client):
        with pytest.raises(RuntimeError) as exc_info:
            await analyzer.analyze_context(context)

        assert "401 Unauthorized" in str(exc_info.value)
        # Must only call once - no wasteful retries on invalid key
        assert call_count == 1


@pytest.mark.asyncio
async def test_context_builder_deduplication_and_capping():
    """Verify AnalysisContextBuilder deduplicates RAG chunks and bounds snippet tokens."""
    builder = AnalysisContextBuilder(max_rag_chunks=3)

    from app.rag.schemas import SearchResponse, SearchResultChunk

    # Create mock search result with duplicates
    mock_chunks = [
        SearchResultChunk(
            chunk_id="chunk_1",
            file_path="other_file.py",
            start_line=10,
            end_line=20,
            language="Python",
            symbol_name="helper",
            content="def helper(): return 42",
            relevance_score=0.9,
            retrieval_method="hybrid",
        ),
        # Identical location (should be deduplicated)
        SearchResultChunk(
            chunk_id="chunk_2",
            file_path="other_file.py",
            start_line=10,
            end_line=20,
            language="Python",
            symbol_name="helper",
            content="def helper(): return 42",
            relevance_score=0.85,
            retrieval_method="hybrid",
        ),
        # Target file self-reference (should be excluded)
        SearchResultChunk(
            chunk_id="chunk_3",
            file_path="target.py",
            start_line=1,
            end_line=5,
            language="Python",
            symbol_name="self_fn",
            content="def self_fn(): pass",
            relevance_score=0.8,
            retrieval_method="hybrid",
        ),
        # Valid distinct chunk
        SearchResultChunk(
            chunk_id="chunk_4",
            file_path="service.py",
            start_line=30,
            end_line=45,
            language="Python",
            symbol_name="service_fn",
            content="def service_fn(): return helper()",
            relevance_score=0.75,
            retrieval_method="hybrid",
        ),
    ]

    mock_search_res = SearchResponse(
        repository_id="test-repo",
        query="test query",
        search_mode="hybrid",
        total_results=4,
        results=mock_chunks,
    )

    with patch("app.rag.service.rag_service.search", new_callable=AsyncMock) as mock_search:
        mock_search.return_value = mock_search_res
        contexts = await builder._retrieve_related_context(
            repository_id="test-repo",
            target_symbol="calc",
            target_file="target.py",
        )

    # Chunks from target.py and duplicate chunk_2 must be excluded
    assert len(contexts) == 2
    paths = [c["file_path"] for c in contexts]
    assert "target.py" not in paths
    assert paths == ["other_file.py", "service.py"]


@pytest.mark.asyncio
async def test_service_repository_timeout_resilience(tmp_path: Path):
    """Verify repository analysis does not fail completely when one file times out."""
    repo_id = "test-repo-timeout-resilience"
    repo_dir = tmp_path / repo_id
    source_dir = repo_dir / "source"
    source_dir.mkdir(parents=True)

    # File 1: will succeed
    (source_dir / "good.py").write_text("def good(): pass\n", encoding="utf-8")
    # File 2: will time out
    (source_dir / "timeout.py").write_text("def slow(): pass\n", encoding="utf-8")

    class PartialTimeoutAnalyzer(MockCodeAnalyzer):
        async def analyze_context(self, context: AnalysisContext):
            if "timeout.py" in context.file_path:
                raise RuntimeError(
                    "Gemini code analysis request timed out after 180.0s: Request timed out. This is a client-side timeout."
                )
            return [
                {
                    "issue_title": "Code Smell in Good",
                    "category": "code_smell",
                    "severity": "Low",
                    "confidence_score": 0.8,
                    "start_line": 1,
                    "end_line": 1,
                    "evidence": "def good(): pass",
                    "technical_explanation": "Empty function",
                    "potential_impact": "None",
                    "suggested_fix": "Add body",
                }
            ]

    service = BugDetectionService(
        analyzer=PartialTimeoutAnalyzer(),
        storage_root=tmp_path,
    )

    run = await service.analyze_repository(repo_id)

    # Repository run must finish with status completed (partial results saved), not 500 crash
    assert run.status == "completed"
    assert run.analyzed_files == 2
    assert run.total_issues == 1
    assert run.error_message is not None
    assert "timeout" in run.error_message.lower()


@pytest.mark.asyncio
async def test_service_file_analysis_timeout_sets_timed_out_status(tmp_path: Path):
    """Verify single-file analysis timeout sets run status to timed_out and saves state."""
    repo_id = "test-repo-file-timeout"
    repo_dir = tmp_path / repo_id
    source_dir = repo_dir / "source"
    source_dir.mkdir(parents=True)

    (source_dir / "slow_file.py").write_text("def heavy(): pass\n", encoding="utf-8")

    class TimeoutOnlyAnalyzer(MockCodeAnalyzer):
        async def analyze_context(self, context: AnalysisContext):
            raise RuntimeError(
                "Gemini code analysis request timed out after 180.0s: Request timed out. This is a client-side timeout."
            )

    service = BugDetectionService(
        analyzer=TimeoutOnlyAnalyzer(),
        storage_root=tmp_path,
    )

    with pytest.raises(RuntimeError):
        await service.analyze_file(repo_id, "slow_file.py")

    latest_run = service._load_latest_local_run(repo_id)
    assert latest_run is not None
    assert latest_run.status == "timed_out"
    assert "timed out after 180" in latest_run.error_message



