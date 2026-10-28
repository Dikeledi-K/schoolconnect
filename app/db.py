"""Database connection setup (SQLAlchemy 2.0).

Only DATABASE_URL changes between SQLite (local) and Supabase Postgres (production).
"""

from collections.abc import Iterator

from datetime import datetime

from sqlalchemy import Column, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Parent class for all ORM models."""


def make_engine(url: str):
    # SQLite needs check_same_thread=False because FastAPI may use the
    # connection from a different thread than the one that created it.
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    # pool_pre_ping avoids errors from stale connections on hosted Postgres.
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True)


engine = make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def init_db(bind=None) -> None:
    """Create missing tables, then add missing columns to old tables (see migrate)."""
    from app import models  # noqa: F401  - import registers the models with Base

    bind = bind or engine
    Base.metadata.create_all(bind=bind)
    migrate(bind)


def _sql_default(value) -> str:
    """A Python default as SQL text that SQLite and Postgres both accept."""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def add_column_sql(table_name: str, column: Column, dialect) -> str:
    """ALTER TABLE ... ADD COLUMN for one model column, written for this database's dialect."""
    sql = f"ALTER TABLE {table_name} ADD COLUMN {column.name} {column.type.compile(dialect=dialect)}"
    default = column.default
    if default is not None and default.is_scalar and not isinstance(default.arg, datetime):
        sql += f" DEFAULT {_sql_default(default.arg)}"
    return sql


def migrate(bind=None) -> list[str]:
    """Week 7: add columns that the models have but an existing database does not.

    SQLAlchemy's create_all only creates MISSING TABLES; it never changes a table that
    already exists. So a Week 6 database would lack e.g. tickets.assigned_to. This compares
    each table with its model and runs ALTER TABLE ... ADD COLUMN only for missing columns.
    It is idempotent (running it again does nothing), never drops anything, and runs at
    every startup. Returns the columns it added, e.g. ["tickets.assigned_to"].
    """
    from app import models  # noqa: F401

    bind = bind or engine
    inspector = inspect(bind)
    added = []
    with bind.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name not in existing:
                    conn.execute(text(add_column_sql(table.name, column, bind.dialect)))
                    added.append(f"{table.name}.{column.name}")
    return added


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
