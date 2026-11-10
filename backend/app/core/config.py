"""Application configuration via Pydantic Settings."""

from pathlib import Path
import re
from typing import Any, Dict, List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Determine backend and project root directory paths
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
ROOT_DIR = BACKEND_DIR.parent

BACKEND_ENV_PATH = BACKEND_DIR / ".env"
ROOT_ENV_PATH = ROOT_DIR / ".env"

# Prioritize backend/.env; fallback to root .env if present; default to backend/.env
ACTIVE_ENV_FILE = (
    BACKEND_ENV_PATH
    if BACKEND_ENV_PATH.is_file()
    else (ROOT_ENV_PATH if ROOT_ENV_PATH.is_file() else BACKEND_ENV_PATH)
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ACTIVE_ENV_FILE),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Project metadata
    PROJECT_NAME: str = "RepoPilot AI"
    VERSION: str = "0.1.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # Server parameters
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    API_V1_PREFIX: str = "/api/v1"

    # CORS origins
    FRONTEND_URL: str = "http://localhost:5173"
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, (list, str)):
            return v
        raise ValueError(v)

    # AI Configuration (Google Gemini)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.8-flash"
    GEMINI_PRO_MODEL: str = "gemini-2.5-pro"

    # AI Analysis & Bug Detection Configuration (Phase 4)
    AI_ANALYSIS_PROVIDER: str = "gemini"  # "gemini" or "mock"
    AI_ANALYSIS_MODEL: str = "gemini-3.8-flash"
    ANALYSIS_MAX_CONCURRENCY: int = 4
    ANALYSIS_MIN_CONFIDENCE: float = 0.4
    ANALYSIS_MAX_CONTEXT_CHUNKS: int = 5
    GEMINI_REQUEST_TIMEOUT: float = 180.0
    ANALYSIS_TIMEOUT: float = 180.0
    ANALYSIS_MAX_RETRIES: int = 3

    # Embedding & RAG Configuration (Phase 3)
    EMBEDDING_PROVIDER: str = "gemini"  # "gemini" or "mock"
    EMBEDDING_MODEL: str = "gemini-embedding-001"
    EMBEDDING_DIMENSION: int = 768
    EMBEDDING_BATCH_SIZE: int = 64
    EMBEDDING_REQUEST_TIMEOUT: float = 60.0
    EMBEDDING_MAX_CONCURRENCY: int = 4
    RAG_TOP_K: int = 10
    RAG_SEMANTIC_WEIGHT: float = 0.6
    RAG_KEYWORD_WEIGHT: float = 0.4
    MAX_CHUNK_LINES: int = 120
    CHUNK_OVERLAP_LINES: int = 20

    # Database (PostgreSQL + pgvector)
    POSTGRES_USER: str = "repopilot"
    POSTGRES_PASSWORD: str = "repopilot_secret"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "repopilot_db"
    DATABASE_URL: str = "postgresql+asyncpg://repopilot:repopilot_secret@localhost:5432/repopilot_db"

    # Workspace & Sandboxing (Phase 6)
    WORKSPACE_STORAGE_PATH: str = "./workspace_storage"
    DOCKER_SANDBOX_TIMEOUT_SECONDS: int = 60
    DOCKER_MAX_MEMORY_MB: int = 2048
    DOCKER_MAX_CPUS: float = 2.0
    DOCKER_PYTHON_IMAGE: str = "python:3.11-slim"
    DOCKER_NODE_IMAGE: str = "node:20-slim"
    DOCKER_NETWORK_MODE: str = "none"
    DOCKER_ALLOW_NETWORK_FOR_DEPS: bool = False

    @property
    def gemini_request_timeout(self) -> float:
        """Effective request timeout in seconds for Gemini API calls."""
        return max(self.GEMINI_REQUEST_TIMEOUT, self.ANALYSIS_TIMEOUT)

    @property
    def is_gemini_configured(self) -> bool:
        """Indicates whether a real, non-placeholder GEMINI_API_KEY is configured."""
        val = (self.GEMINI_API_KEY or "").strip()
        if not val:
            return False
        if val.lower() in (
            "your_gemini_api_key_here",
            "your_gemini_api_key",
            "none",
            "placeholder",
            "changeme",
        ):
            return False
        if val.startswith("your_"):
            return False
        return True

    @property
    def masked_gemini_key(self) -> str:
        """Safely masks GEMINI_API_KEY for logs and diagnostics (e.g., 'AIza...1234')."""
        if not self.is_gemini_configured:
            return "<not configured>"
        key = self.GEMINI_API_KEY.strip()
        if len(key) <= 8:
            return "****"
        return f"{key[:4]}...{key[-4:]}"

    @property
    def ai_analysis_mode(self) -> str:
        """Operational mode for AI Code Analysis: 'online' or 'offline'."""
        if self.AI_ANALYSIS_PROVIDER.lower().strip() == "mock":
            return "offline"
        if not self.is_gemini_configured:
            return "offline"
        return "online"

    @property
    def embedding_mode(self) -> str:
        """Operational mode for Embeddings & RAG: 'online' or 'offline'."""
        if self.EMBEDDING_PROVIDER.lower().strip() == "mock":
            return "offline"
        if not self.is_gemini_configured:
            return "offline"
        return "online"

    @property
    def normalized_embedding_model(self) -> str:
        """Returns active embedding model name, migrating legacy text-embedding-004 to gemini-embedding-001."""
        model = self.EMBEDDING_MODEL.strip()
        if model in ("text-embedding-004", "models/text-embedding-004"):
            return "gemini-embedding-001"
        return model

    @property
    def safe_database_url(self) -> str:
        """Returns DATABASE_URL with sensitive password credentials masked."""
        if not self.DATABASE_URL:
            return "<unconfigured>"
        return re.sub(r"://([^:]+):([^@]+)@", r"://\1:****@", self.DATABASE_URL)


settings = Settings()


def validate_configuration() -> Dict[str, Any]:
    """Validates runtime configuration and emits structured status logs without leaking credentials."""
    from app.core.logging import logger

    logger.info("================ Configuration Validation ================")
    logger.info(
        "Project: %s v%s (Environment: %s)",
        settings.PROJECT_NAME,
        settings.VERSION,
        settings.ENVIRONMENT,
    )
    logger.info("Active Environment File: %s", ACTIVE_ENV_FILE)

    # 1. Gemini Credentials Validation
    if settings.is_gemini_configured:
        logger.info("Gemini Credentials: CONFIGURED [Key: %s]", settings.masked_gemini_key)
    else:
        logger.info(
            "Gemini Credentials: NOT CONFIGURED (Empty/Placeholder). Application running in OFFLINE mode for AI subsystems."
        )

    # 2. AI Code Analysis Provider Status
    analysis_prov = settings.AI_ANALYSIS_PROVIDER.lower().strip()
    if analysis_prov == "mock":
        logger.info("AI Code Analysis: OFFLINE mode explicitly configured (Provider: mock).")
    elif settings.is_gemini_configured:
        logger.info(
            "AI Code Analysis: ONLINE mode active (Provider: %s, Model: %s).",
            settings.AI_ANALYSIS_PROVIDER,
            settings.AI_ANALYSIS_MODEL,
        )
    else:
        logger.info(
            "AI Code Analysis: OFFLINE mode active (Provider '%s' requested, falling back to MockCodeAnalyzer because GEMINI_API_KEY is not set).",
            settings.AI_ANALYSIS_PROVIDER,
        )

    # 3. Embedding Provider Status
    embed_prov = settings.EMBEDDING_PROVIDER.lower().strip()
    if embed_prov == "mock":
        logger.info("Code Embeddings / RAG: OFFLINE mode explicitly configured (Provider: mock).")
    elif settings.is_gemini_configured:
        logger.info(
            "Code Embeddings / RAG: ONLINE mode active (Provider: %s, Model: %s, Dimension: %d).",
            settings.EMBEDDING_PROVIDER,
            settings.EMBEDDING_MODEL,
            settings.EMBEDDING_DIMENSION,
        )
    else:
        logger.info(
            "Code Embeddings / RAG: OFFLINE mode active (Provider '%s' requested, falling back to MockEmbeddingProvider because GEMINI_API_KEY is not set).",
            settings.EMBEDDING_PROVIDER,
        )

    # 4. Database Configuration
    logger.info("Database Connection: %s", settings.safe_database_url)

    # 5. Storage Directory
    storage_path = Path(settings.WORKSPACE_STORAGE_PATH)
    try:
        storage_path.mkdir(parents=True, exist_ok=True)
        logger.info("Workspace Storage Directory: Ready (%s)", storage_path.resolve())
    except Exception as e:
        logger.warning("Workspace Storage path creation error: %s", e)

    logger.info("==========================================================")

    return {
        "env_file": str(ACTIVE_ENV_FILE),
        "gemini_configured": settings.is_gemini_configured,
        "ai_analysis_mode": settings.ai_analysis_mode,
        "embedding_mode": settings.embedding_mode,
        "database_url_safe": settings.safe_database_url,
    }
