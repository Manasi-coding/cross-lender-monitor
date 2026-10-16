"""SPEC test 6: ingesting the same accession_number twice leaves row counts unchanged.
Uses insert_filing with synthetic rows, so no network and no filing document are needed."""
from datetime import date

import psycopg
import pytest

from pipeline.ingest import HashMismatch, insert_filing

FILING = {
    "cik": "0000000001", "bdc_name": "Test BDC", "form_type": "10-Q", "period_end": date(2026, 6, 30),
    "filing_date": date(2026, 8, 10), "accession": "0000000000-26-000001",
    "source_url": "https://example.test/filing.htm",
}
HOLDINGS = [
    # name, industry, instrument, rate, maturity, principal, unit, cost, fair value, footnotes, row_order, source_url
    ("Acme Holdings, LLC", None, "First Lien Secured Debt - Term Loan", "S+500", "01/01/2030",
     "1000000", "U_USD", "990000", "985000", None, 1, FILING["source_url"]),
    ("Beta Corp", None, "First Lien Secured Debt - Revolver", None, None,
     None, None, "-1000", "-2000", None, 2, FILING["source_url"]),
]


def _counts(conn) -> tuple[int, int]:
    return (conn.execute("SELECT count(*) FROM raw_filings").fetchone()[0],
            conn.execute("SELECT count(*) FROM raw_holdings").fetchone()[0])


def test_second_ingest_changes_nothing(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        status1, filing_id, n1 = insert_filing(conn, FILING, HOLDINGS, "a" * 64)
        counts1 = _counts(conn)
        status2, filing_id2, n2 = insert_filing(conn, FILING, HOLDINGS, "a" * 64)
        counts2 = _counts(conn)
    assert (status1, n1) == ("loaded", 2)
    assert (status2, n2) == ("unchanged", 0)
    assert filing_id2 == filing_id
    assert counts1 == counts2 == (1, 2)


def test_changed_document_is_refused_on_second_run(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        insert_filing(conn, FILING, HOLDINGS, "a" * 64)
        with pytest.raises(HashMismatch):
            insert_filing(conn, FILING, HOLDINGS, "b" * 64)
        assert _counts(conn) == (1, 2)


def test_filing_loaded_before_hashes_existed_gets_its_hash_once(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        conn.execute(
            "INSERT INTO raw_filings (cik, bdc_name, form_type, period_end_date, filing_date, "
            "accession_number, source_url) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (FILING["cik"], FILING["bdc_name"], FILING["form_type"], FILING["period_end"],
             FILING["filing_date"], FILING["accession"], FILING["source_url"]),
        )
        status, _, n = insert_filing(conn, FILING, HOLDINGS, "c" * 64)
        stored = conn.execute("SELECT source_sha256 FROM raw_filings").fetchone()[0]
        status_again, _, _ = insert_filing(conn, FILING, HOLDINGS, "c" * 64)
    assert (status, n) == ("hash_recorded", 0)
    assert stored == "c" * 64
    assert status_again == "unchanged"
