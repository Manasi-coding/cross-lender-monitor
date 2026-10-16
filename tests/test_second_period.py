"""SPEC test 26 (the part that can run on Day 4): a non-measured quarter loads as its own filing and
period, and nothing from it can reach label_samples. The facility and E5 part needs compare.py.

The second period is a real excerpt of the ADS 10-Q for 2026-03-31 (a separate filing, accession
0001193125-26-215667), not the comparative column of the 2026-06-30 filing."""
from datetime import date
from pathlib import Path

import psycopg

from pipeline.adapters import Filing, make_adapter
from pipeline.config import load_config
from pipeline.ingest import insert_filing

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
CFG = load_config()["filers"]["ads"]


def _load(conn, fixture: str, period: date, accession: str, url: str) -> int:
    adapter = make_adapter("ads", CFG)
    rows = adapter.parse(Filing("ads", CFG["cik"], "Apollo Debt Solutions BDC", period, FIXTURES / fixture, url, accession))
    meta = {"cik": CFG["cik"], "bdc_name": "Apollo Debt Solutions BDC", "form_type": "10-Q", "period_end": period,
            "filing_date": date(2026, 8, 10), "accession": accession, "source_url": url}
    status, _, n = insert_filing(conn, meta, rows, "f" * 64)
    assert status == "loaded"
    return n


def test_second_quarter_loads_as_its_own_period_and_stays_out_of_labels(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        n_measured = _load(conn, "ads_excerpt.htm", date(2026, 6, 30), "0001193125-26-341358", "https://example.test/q2.htm")
        n_second = _load(conn, "ads_q1_excerpt.htm", date(2026, 3, 31), "0001193125-26-215667", "https://example.test/q1.htm")
        periods = conn.execute("SELECT period_end_date, count(*) FROM raw_filings f JOIN raw_holdings h USING (filing_id) "
                               "GROUP BY 1 ORDER BY 1").fetchall()
        assert periods == [(date(2026, 3, 31), n_second), (date(2026, 6, 30), n_measured)]
        assert (n_measured, n_second) == (28, 10)
        # no holding from the second quarter is in a sample, and nothing has been sampled at all
        assert conn.execute("SELECT count(*) FROM label_samples").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM candidate_pairs").fetchone()[0] == 0
        urls = {r[0] for r in conn.execute("SELECT DISTINCT source_url FROM raw_holdings")}
        assert urls == {"https://example.test/q2.htm", "https://example.test/q1.htm"}
