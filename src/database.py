from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg import Connection

from config import settings


def _get_psycopg_dsn() -> str:
    database_url = settings().database_url
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not configured. Set it in the environment or .env."
        )

    # SQLAlchemy-style URLs are accepted by Alembic but psycopg expects a
    # PostgreSQL DSN without the driver suffix.
    for sqlalchemy_scheme in ("postgresql+psycopg://", "postgres+psycopg://"):
        if database_url.startswith(sqlalchemy_scheme):
            return database_url.replace(sqlalchemy_scheme, "postgresql://", 1)

    return database_url


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
