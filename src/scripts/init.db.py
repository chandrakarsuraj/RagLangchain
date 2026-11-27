from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit

import psycopg

# Allow running this file directly from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import settings  # noqa: E402
from database import get_db_connection  # noqa: E402

EXPECTED_TABLES = {
    "documents",
    "feedback",
    "audit_events",
    "approvals",
    "chat_messages",
}
EXPECTED_REVISION = "20261127_0001"


def _validate_database_url() -> bool:
    database_url = settings().database_url
    if not database_url:
        print("DATABASE_URL is not configured.", file=sys.stderr)
        return False

    query_keys = {
        key for key, _ in parse_qsl(urlsplit(database_url).query, keep_blank_values=True)
    }
    if any(key.startswith("?") for key in query_keys):
        print(
            "DATABASE_URL has an extra '?' before a query option. "
            "Use one '?' before options such as sslmode (not '??sslmode').",
            file=sys.stderr,
        )
        return False

    return True


def main() -> int:
    if not _validate_database_url():
        return 1

    try:
        with get_db_connection() as connection:
            # Make this diagnostic explicitly read-only.
            connection.execute("SET TRANSACTION READ ONLY")
            schema = connection.execute("SELECT current_schema()").fetchone()[0]
            table_rows = connection.execute(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = current_schema()
                  AND table_type = 'BASE TABLE'
                """
            ).fetchall()
            existing_tables = {row[0] for row in table_rows}

            if "alembic_version" in existing_tables:
                version_rows = connection.execute(
                    "SELECT version_num FROM alembic_version ORDER BY version_num"
                ).fetchall()
                revisions = [row[0] for row in version_rows]
            else:
                revisions = []

    except (psycopg.Error, RuntimeError, ValueError) as exc:
        print(
            f"Database verification failed ({type(exc).__name__}). "
            "Check DATABASE_URL, network access, and PostgreSQL availability.",
            file=sys.stderr,
        )
        return 1

    missing_tables = sorted(EXPECTED_TABLES - existing_tables)
    revision_ok = revisions == [EXPECTED_REVISION]

    print(f"Database connection: OK (schema: {schema})")
    print("Table checks:")
    for table in sorted(EXPECTED_TABLES):
        status = "OK" if table in existing_tables else "MISSING"
        print(f"  {table}: {status}")

    if revisions:
        print(f"Alembic revision: {', '.join(revisions)}")
    else:
        print("Alembic revision: MISSING (alembic_version table or revision not found)")

    if missing_tables or not revision_ok:
        print("Verification: FAILED")
        return 1

    print("Verification: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
