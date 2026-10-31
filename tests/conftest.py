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


# ---------------------------------------------------------------- synthetic normalized rows for matching tests
from datetime import date as _date  # noqa: E402
from decimal import Decimal as _Decimal  # noqa: E402


def seed_normalized(conn, rows: list[dict]) -> list[int]:
    """Insert synthetic rows into raw_filings, raw_holdings and normalized_holdings. Each dict needs bdc_cik,
    period_end_date, borrower_normalized, instrument_type_norm; maturity_date, spread_bps, principal, fair_value_pct_par, excluded_reason, reference_rate are optional.
    Returns the holding ids in order."""
    ids = []
    filings: dict[tuple, int] = {}
    for i, r in enumerate(rows):
        key = (r["bdc_cik"], r["period_end_date"])
        if key not in filings:
            filings[key] = conn.execute(
                "INSERT INTO raw_filings (cik, bdc_name, form_type, period_end_date, filing_date, accession_number, source_url) "
                "VALUES (%s, %s, '10-Q', %s, %s, %s, 'https://example.test/f') RETURNING filing_id",
                (r["bdc_cik"], "BDC " + r["bdc_cik"], r["period_end_date"], _date(2026, 8, 1),
                 f"acc-{r['bdc_cik']}-{r['period_end_date']}")).fetchone()[0]
        hid = conn.execute(
            "INSERT INTO raw_holdings (filing_id, portfolio_company_raw, row_order, source_url) VALUES (%s, %s, %s, 'https://example.test/f') "
            "RETURNING holding_id", (filings[key], r["borrower_normalized"], i)).fetchone()[0]
        conn.execute(
            "INSERT INTO normalized_holdings (holding_id, bdc_cik, period_end_date, borrower_normalized, instrument_type_norm, "
            "maturity_date, spread_bps, principal, fair_value_pct_par, excluded_reason, reference_rate, source_url) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'https://example.test/f')",
            (hid, r["bdc_cik"], r["period_end_date"], r["borrower_normalized"], r["instrument_type_norm"],
             r.get("maturity_date"), r.get("spread_bps"), r.get("principal"), r.get("fair_value_pct_par"),
             r.get("excluded_reason"), r.get("reference_rate")))
        extra = {k: r[k] for k in ("cost", "fair_value", "floor_bps", "pik_bps", "non_accrual") if k in r}
        for col, val in extra.items():                       # optional dossier columns
            conn.execute(f"UPDATE normalized_holdings SET {col} = %s WHERE holding_id = %s", (val, hid))
        ids.append(hid)
    return ids
