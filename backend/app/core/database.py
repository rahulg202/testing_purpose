"""Database connection and session management.

Uses SQLAlchemy 2.0 async. The driver is chosen by the URL, so the same code
runs against SQLite (local prototype, tests) and PostgreSQL (self-hosted, via
Docker Compose) with no change.
"""

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import get_settings


@lru_cache
def get_engine() -> AsyncEngine:
    """The process-wide async engine.

    Cached because creating an engine per request leaks connection pools.
    SQLite ignores pool sizing; PostgreSQL honours it.
    """
    settings = get_settings()
    kwargs: dict[str, object] = {"echo": settings.database_echo}
    if not settings.database_url.startswith("sqlite"):
        kwargs.update({"pool_size": 5, "max_overflow": 10, "pool_pre_ping": True})
    return create_async_engine(settings.database_url, **kwargs)


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Cached session factory bound to the shared engine."""
    return async_sessionmaker(get_engine(), class_=AsyncSession, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a database session.

    Rolls back on error so a failed request cannot leave a half-applied
    transaction behind; route handlers commit explicitly on success.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
