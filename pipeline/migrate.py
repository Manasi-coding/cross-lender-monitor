"""Minimal migration runner. Applies db/migrations/NNN_*.sql in order, once each.

Run: python -m pipeline.migrate
Applied files are recorded in schema_migrations. Each file runs in its own transaction.
Parameterized SQL only: the file contents are the only dynamic SQL, and they are repo files.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg

from pipeline.config import load_env_file

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "db" / "migrations"


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not set.")
    return url


def apply_migrations(conn: psycopg.Connection, directory: Path = MIGRATIONS_DIR) -> list[str]:
    with conn.transaction():
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
        )
    done = {r[0] for r in conn.execute("SELECT filename FROM schema_migrations").fetchall()}
    applied: list[str] = []
    for path in sorted(directory.glob("[0-9][0-9][0-9]_*.sql")):
        if path.name in done:
            continue
        with conn.transaction():
            conn.execute(path.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,))
        applied.append(path.name)
    return applied


def main() -> int:
    load_env_file()
    with psycopg.connect(database_url()) as conn:
        applied = apply_migrations(conn)
    print("applied:", ", ".join(applied) if applied else "nothing to apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
