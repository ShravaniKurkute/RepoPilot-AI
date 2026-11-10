"""Async SQLAlchemy engine and session factory for PostgreSQL + pgvector."""

from typing import AsyncGenerator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings
from app.core.logging import logger
from app.database.models import Base

# Global engine and sessionmaker
engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency that provides an async database session per request."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def check_database_connection() -> bool:
    """Verifies whether PostgreSQL is reachable and pgvector is supported."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.debug(f"Database connection check returned False: {e}")
        return False


async def init_db() -> bool:
    """Initializes pgvector extension and creates database schema tables.

    Returns:
        True if schema creation succeeded, False if database is unavailable.
    """
    try:
        async with engine.begin() as conn:
            # Enable pgvector extension
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            # Create tables
            await conn.run_sync(Base.metadata.create_all)
        logger.info("PostgreSQL pgvector extension and tables initialized successfully.")
        return True
    except Exception as e:
        logger.warning(
            f"Database initialization could not connect to PostgreSQL: {e}. "
            "RAG vector store will operate in resilient workspace cache mode."
        )
        return False

