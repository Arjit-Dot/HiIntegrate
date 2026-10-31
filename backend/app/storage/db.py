"""The database connection (D-10). Postgres in Compose, SQLite for tests, chosen by DATABASE_URL."""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import get_settings
from app.storage.models import Base


def make_engine(url: str) -> Engine:
    kwargs = {"connect_args": {"check_same_thread": False}} if url.startswith("sqlite") else {"pool_pre_ping": True}
    return create_engine(url, **kwargs)


class SchemaOutOfDate(RuntimeError):
    """The database was made by an older version of the app (D-18 added an `account` column to most tables)."""


def check_schema(engine: Engine) -> None:
    """Stop with a clear message when an existing table lacks a column this version needs. create_all never alters a table,
    so without this check the first query would fail with an obscure SQL error (D-18)."""
    have = inspect(engine)
    problems = []
    for table in Base.metadata.sorted_tables:
        if not have.has_table(table.name):
            continue
        existing = {c["name"] for c in have.get_columns(table.name)}
        missing = [c.name for c in table.columns if c.name not in existing]
        if missing:
            problems.append(f"table {table.name} has no column {', '.join(missing)}")
    if problems:
        raise SchemaOutOfDate(
            "The database was created by an older version of this app and does not match it: " + "; ".join(problems) + ". "
            "Recreate it: run `docker compose down -v` (this DELETES the stored data), or, for a local SQLite file, delete the file "
            "named in DATABASE_URL. Old data cannot be moved into accounts automatically (D-18)."
        )


def init_db(engine: Engine) -> None:
    Base.metadata.create_all(engine)  # tables are created at startup in v1 (D-10); migrations are a stretch
    check_schema(engine)


@lru_cache
def get_engine() -> Engine:
    engine = make_engine(get_settings().database_url)
    init_db(engine)
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
