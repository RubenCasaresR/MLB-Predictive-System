import functools
import os

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def _build_engine(db_url: str) -> Engine:
    return create_engine(
        db_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
    )


@functools.lru_cache(maxsize=2)
def _cached_engine(db_url: str) -> Engine:
    return _build_engine(db_url)


def get_engine() -> Engine:
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://mlb_user:@localhost:5432/mlb_predictive",
    )
    return _cached_engine(db_url)


def _sync_to_async_url(url: str) -> str:
    if url.startswith("sqlite://"):
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    return url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _build_async_engine(db_url: str):
    async_url = _sync_to_async_url(db_url)
    return create_async_engine(
        async_url,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=3600,
    )


@functools.lru_cache(maxsize=2)
def _cached_async_engine(db_url: str):
    return _build_async_engine(db_url)


def get_async_engine():
    db_url = os.getenv(
        "DATABASE_URL",
        "postgresql://mlb_user:@localhost:5432/mlb_predictive",
    )
    return _cached_async_engine(db_url)


async def get_async_session() -> AsyncSession:
    engine = get_async_engine()
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
