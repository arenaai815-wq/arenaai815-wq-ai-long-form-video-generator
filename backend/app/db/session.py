"""Async engine/session for the API and a sync engine/session for workers."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

_engine_kwargs: dict = {"echo": settings.database_echo, "pool_pre_ping": True}
if not settings.database_url.startswith("sqlite"):
    _engine_kwargs.update(
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
    )

async_engine = create_async_engine(settings.database_url, **_engine_kwargs)
AsyncSessionLocal = async_sessionmaker(async_engine, expire_on_commit=False, class_=AsyncSession)

_sync_engine = None
_SyncSessionLocal: sessionmaker | None = None


def get_sync_engine():
    global _sync_engine, _SyncSessionLocal
    if _sync_engine is None:
        kwargs: dict = {"echo": settings.database_echo, "pool_pre_ping": True}
        if not settings.sync_database_url.startswith("sqlite"):
            kwargs.update(pool_size=5, max_overflow=10)
        _sync_engine = create_engine(settings.sync_database_url, **kwargs)
        _SyncSessionLocal = sessionmaker(_sync_engine, expire_on_commit=False, class_=Session)
    return _sync_engine


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a request-scoped session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@contextmanager
def sync_session() -> Iterator[Session]:
    """Context manager used by Celery tasks (sync workers)."""
    get_sync_engine()
    assert _SyncSessionLocal is not None
    session = _SyncSessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
