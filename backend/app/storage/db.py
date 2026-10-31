"""The database connection (D-10). Postgres in Compose, SQLite for tests, chosen by DATABASE_URL."""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import get_settings
from app.storage.models import Base


def make_engine(url: str) -> Engine:
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True}
    return create_engine(url, **kwargs)


@lru_cache
def get_engine() -> Engine:
    engine = make_engine(get_settings().database_url)
    Base.metadata.create_all(engine)  # tables are created at startup in v1 (D-10); migrations are a stretch
    return engine


def session_factory(engine: Engine | None = None) -> sessionmaker:
    return sessionmaker(bind=engine or get_engine(), expire_on_commit=False)


@contextmanager
def session_scope(engine: Engine | None = None) -> Iterator[Session]:
    session = session_factory(engine)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
