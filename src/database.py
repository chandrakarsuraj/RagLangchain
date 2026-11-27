from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg import Connection

from config import settings


def get_sqlalchemy_database_url(database_url: str | None = None) -> str:
    """Return DATABASE_URL normalized for SQLAlchemy's psycopg 3 driver."""
    database_url = database_url or settings().database_url
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not configured. Set it in the environment or .env."
        )

    if database_url.startswith("postgresql+psycopg://"):
        return database_url

    for scheme in ("postgresql://", "postgres://", "postgres+psycopg://"):
        if database_url.startswith(scheme):
            return database_url.replace(scheme, "postgresql+psycopg://", 1)

    raise ValueError(
        "DATABASE_URL must be a PostgreSQL URL, such as "
        "postgresql+psycopg://user:password@host:5432/database."
    )


def _get_psycopg_dsn() -> str:
    # psycopg.connect() accepts the PostgreSQL DSN without SQLAlchemy's driver suffix.
    sqlalchemy_url = get_sqlalchemy_database_url()
    return sqlalchemy_url.replace("postgresql+psycopg://", "postgresql://", 1)


@contextmanager
def get_db_connection() -> Iterator[Connection]:
    """Open a psycopg connection and close it when the context exits.

    The psycopg connection context commits on success and rolls back on error.
    """
    with psycopg.connect(_get_psycopg_dsn(), connect_timeout=10) as connection:
        yield connection


def check_database_connection() -> bool:
    """Return True when a simple query can be executed against PostgreSQL."""
    with get_db_connection() as connection:
        row = connection.execute("SELECT 1").fetchone()
        return row is not None and row[0] == 1
