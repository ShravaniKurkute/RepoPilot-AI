"""Unit and integration tests for environment configuration, .env loading, and Gemini integration."""

from pathlib import Path
import re
import pytest
from unittest.mock import patch, AsyncMock

from app.analysis.analyzer import GeminiCodeAnalyzer, MockCodeAnalyzer, get_code_analyzer
from app.analysis.context_builder import AnalysisContext
from app.core.config import Settings, ACTIVE_ENV_FILE, validate_configuration, settings
from app.rag.embeddings import GeminiEmbeddingProvider, MockEmbeddingProvider, get_embedding_provider


def test_env_file_resolved_to_backend():
    """Verify that configuration targets backend/.env reliably regardless of working directory."""
    assert ACTIVE_ENV_FILE.name == ".env"
    assert "backend" in str(ACTIVE_ENV_FILE)
    assert ACTIVE_ENV_FILE.is_file()


def test_env_variables_loaded_correctly():
    """Verify all primary application settings are loaded with valid types."""
    assert settings.PROJECT_NAME == "RepoPilot AI"
    assert settings.ENVIRONMENT in ("development", "test", "production")
    assert settings.APP_PORT == 8000
    assert settings.FRONTEND_URL == "http://localhost:5173"

    # AI & Embeddings
    assert settings.AI_ANALYSIS_MODEL == "gemini-3.8-flash"
    assert settings.EMBEDDING_MODEL in ("gemini-embedding-001", "text-embedding-004")
    assert settings.EMBEDDING_DIMENSION == 768
    assert settings.EMBEDDING_BATCH_SIZE == 64

    # RAG
    assert settings.RAG_TOP_K == 10
    assert settings.RAG_SEMANTIC_WEIGHT == 0.6
    assert settings.RAG_KEYWORD_WEIGHT == 0.4

    # Analysis
    assert settings.ANALYSIS_MAX_CONCURRENCY == 4
    assert settings.ANALYSIS_MIN_CONFIDENCE == 0.4
    assert settings.ANALYSIS_MAX_CONTEXT_CHUNKS == 5
    assert settings.GEMINI_REQUEST_TIMEOUT == 180.0
    assert settings.ANALYSIS_TIMEOUT == 180.0
    assert settings.ANALYSIS_MAX_RETRIES == 3
    assert settings.gemini_request_timeout == 180.0

    # Database
    assert "postgresql+asyncpg://" in settings.DATABASE_URL
    assert settings.POSTGRES_DB == "repopilot_db"


def test_placeholder_credentials_and_offline_mode():
    """Verify that empty or placeholder credentials safely activate Offline Mode."""
    test_settings = Settings(GEMINI_API_KEY="")
    assert not test_settings.is_gemini_configured
    assert test_settings.masked_gemini_key == "<not configured>"
    assert test_settings.ai_analysis_mode == "offline"
    assert test_settings.embedding_mode == "offline"

    # Placeholder test
    placeholder_settings = Settings(GEMINI_API_KEY="your_gemini_api_key_here")
    assert not placeholder_settings.is_gemini_configured
    assert placeholder_settings.masked_gemini_key == "<not configured>"


def test_gemini_key_accessible_when_configured():
    """Verify that when a real key is provided, it is accessible to analyzer and embedding provider."""
    dummy_key = "AIzaSyValidDummyTestKey1234567890"
    test_settings = Settings(
        GEMINI_API_KEY=dummy_key,
        AI_ANALYSIS_PROVIDER="gemini",
        EMBEDDING_PROVIDER="gemini",
    )
    assert test_settings.is_gemini_configured
    assert test_settings.masked_gemini_key == "AIza...7890"
    assert test_settings.ai_analysis_mode == "online"
    assert test_settings.embedding_mode == "online"

    # Analyzer access
    analyzer = GeminiCodeAnalyzer(api_key=dummy_key, model_name=test_settings.AI_ANALYSIS_MODEL)
    assert analyzer._api_key == dummy_key
    assert analyzer.provider_name == f"gemini ({test_settings.AI_ANALYSIS_MODEL})"

    # Embedding provider access
    embedder = GeminiEmbeddingProvider(
        api_key=dummy_key,
        model_name=test_settings.EMBEDDING_MODEL,
        dimension=test_settings.EMBEDDING_DIMENSION,
    )
    assert embedder._api_key == dummy_key
    assert embedder.dimension == 768


def test_provider_factories_offline_mode():
    """Verify provider factories cleanly yield mock providers when unconfigured."""
    with patch("app.core.config.settings.GEMINI_API_KEY", ""):
        with patch("app.core.config.settings.AI_ANALYSIS_PROVIDER", "gemini"):
            analyzer = get_code_analyzer()
            assert isinstance(analyzer, MockCodeAnalyzer)
            assert "offline" in analyzer.provider_name

        with patch("app.core.config.settings.EMBEDDING_PROVIDER", "gemini"):
            embedder = get_embedding_provider()
            assert isinstance(embedder, MockEmbeddingProvider)
            assert embedder.dimension == 768


def test_independent_provider_configurations():
    """Verify AI analysis and RAG embeddings can be configured independently."""
    # Analysis mock, Embedding gemini
    with patch("app.core.config.settings.GEMINI_API_KEY", "AIzaSyTestKeyDummy12345"):
        with patch("app.core.config.settings.AI_ANALYSIS_PROVIDER", "mock"):
            with patch("app.core.config.settings.EMBEDDING_PROVIDER", "gemini"):
                analyzer = get_code_analyzer()
                embedder = get_embedding_provider()
                assert isinstance(analyzer, MockCodeAnalyzer)
                assert isinstance(embedder, GeminiEmbeddingProvider)

        # Analysis gemini, Embedding mock
        with patch("app.core.config.settings.AI_ANALYSIS_PROVIDER", "gemini"):
            with patch("app.core.config.settings.EMBEDDING_PROVIDER", "mock"):
                analyzer = get_code_analyzer()
                embedder = get_embedding_provider()
                assert isinstance(analyzer, GeminiCodeAnalyzer)
                assert isinstance(embedder, MockEmbeddingProvider)


def test_no_credentials_exposed_in_safe_database_url_and_logs():
    """Verify passwords in DATABASE_URL are masked and secrets are not leaked."""
    raw_url = "postgresql+asyncpg://repopilot:super_secret_password_123@localhost:5432/repopilot_db"
    test_settings = Settings(DATABASE_URL=raw_url)

    safe_url = test_settings.safe_database_url
    assert "super_secret_password_123" not in safe_url
    assert "repopilot:****@" in safe_url

    # Check key masking
    key = "AIzaSySecretApiKey9999"
    test_settings_key = Settings(GEMINI_API_KEY=key)
    masked = test_settings_key.masked_gemini_key
    assert key not in masked
    assert masked == "AIza...9999"


def test_validate_configuration_runs_safely():
    """Verify configuration validation runs on startup without exceptions."""
    status = validate_configuration()
    assert isinstance(status, dict)
    assert "env_file" in status
    assert "ai_analysis_mode" in status
    assert "embedding_mode" in status
    assert "database_url_safe" in status
    assert "repopilot_secret" not in status["database_url_safe"]


@pytest.mark.asyncio
async def test_gemini_analyzer_failure_raises_and_never_silently_replaces_with_mock():
    """Verify Gemini failure raises RuntimeError and does NOT silently return mock results."""
    analyzer = GeminiCodeAnalyzer(api_key="AIzaSyDummyKey", max_retries=1)
    context = AnalysisContext(
        repository_id="test-repo",
        file_path="main.py",
        language="Python",
        target_code="def broken(): pass",
        start_line=1,
        end_line=1,
    )

    mock_client = AsyncMock()
    mock_client.aio.interactions.create.side_effect = Exception("HTTP 500: Internal Server Error")
    mock_client.aio.models.generate_content.side_effect = Exception("HTTP 500: Internal Server Error")

    with patch.object(analyzer, "_get_client", return_value=mock_client):
        with pytest.raises(RuntimeError) as exc_info:
            await analyzer.analyze_context(context)
        assert "Gemini code analysis failed" in str(exc_info.value) or "Gemini API error" in str(exc_info.value)


@pytest.mark.asyncio
async def test_gemini_embedding_failure_raises_and_never_silently_replaces_with_mock():
    """Verify Gemini embedding failure raises RuntimeError and does NOT silently return mock vectors."""
    provider = GeminiEmbeddingProvider(api_key="AIzaSyDummyKey", max_retries=1)

    mock_response = AsyncMock()
    mock_response.status_code = 401
    mock_response.text = "Unauthorized: API key invalid"

    with patch("httpx.AsyncClient.post", return_value=mock_response):
        with pytest.raises(RuntimeError) as exc_info:
            await provider.embed_batch(["text chunk"])
        assert "Gemini Embedding API error" in str(exc_info.value) or "failed after" in str(exc_info.value)


def test_git_exclusion_rules():
    """Verify .gitignore files explicitly exclude .env and protect .env.example."""
    backend_dir = Path(__file__).resolve().parent.parent
    root_dir = backend_dir.parent

    root_gitignore = (root_dir / ".gitignore").read_text(encoding="utf-8")
    backend_gitignore = (backend_dir / ".gitignore").read_text(encoding="utf-8")

    # Both must explicitly ignore .env and *.env
    assert ".env" in root_gitignore
    assert "*.env" in root_gitignore
    assert "backend/.env" in root_gitignore
    assert "!*.env.example" in root_gitignore

    assert ".env" in backend_gitignore
    assert "!*.env.example" in backend_gitignore

