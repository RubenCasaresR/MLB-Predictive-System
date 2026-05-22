import os
import functools
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


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
