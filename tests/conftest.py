"""Shared fixtures. Database tests need a reachable Postgres in DATABASE_URL (CI service container
or the compose db published on localhost). Each test gets its own scratch database."""
from __future__ import annotations

import os
import uuid
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest

from pipeline.migrate import apply_migrations


def _with_db(url: str, dbname: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path="/" + dbname))


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        pytest.skip("DATABASE_URL is not set")
    return url


@pytest.fixture()
def empty_db(database_url: str):
    """Yield the URL of a new, empty scratch database and drop it afterwards."""
    name = "test_" + uuid.uuid4().hex[:12]
    with psycopg.connect(_with_db(database_url, "postgres"), autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    try:
        yield _with_db(database_url, name)
    finally:
        with psycopg.connect(_with_db(database_url, "postgres"), autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture()
def migrated_db(empty_db: str):
    with psycopg.connect(empty_db) as conn:
        apply_migrations(conn)
    return empty_db
