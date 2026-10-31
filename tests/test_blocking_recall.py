"""blocking_recall.py: the seeded draw, the worksheet, record and finalize (SPEC 12.5). Synthetic holdings."""
import copy
import json
from datetime import date
from decimal import Decimal

import psycopg
import pytest

from pipeline import blocking_recall as br
from pipeline.config import load_config

from conftest import seed_normalized

CFG = load_config()
P2, P1 = date(2026, 6, 30), date(2026, 3, 31)
CIKS = ["0000000001", "0000000002", "0000000003"]


def holdings(conn, n=20):
    rows = [{"bdc_cik": CIKS[i % 3], "period_end_date": P2, "borrower_normalized": f"borrower{i:02d}", "instrument_type_norm": "FIRST_LIEN",
             "maturity_date": date(2030, 1, 31), "spread_bps": Decimal(500)} for i in range(n)]
    rows += [{"bdc_cik": CIKS[0], "period_end_date": P1, "borrower_normalized": "prior0", "instrument_type_norm": "FIRST_LIEN"},
             {"bdc_cik": CIKS[1], "period_end_date": P1, "borrower_normalized": "prior1", "instrument_type_norm": "FIRST_LIEN"}]
    return seed_normalized(conn, rows)


def test_config_numbers():
    assert CFG["blocking_recall"] == {"sample_size": 30, "seed": 1}


def test_the_draw_is_30_when_there_are_enough_deterministic_measured_period_only_and_sorted(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        ids = holdings(conn, 60)
        d1, d2 = br.draw(conn, P2, CFG), br.draw(conn, P2, CFG)
        other = copy.deepcopy(CFG)
        other["blocking_recall"]["seed"] = 2
        d3 = br.draw(conn, P2, other)
        prior = set(ids[60:])
    assert len(d1) == 30 and d1 == d2 and d1 == sorted(d1) and len(set(d1)) == 30
    assert not prior & set(d1) and d3 != d1                                              # the prior quarter is never drawn; the seed matters
    assert set(d1) <= set(ids[:60])


def test_a_small_pool_is_drawn_in_full(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        holdings(conn, 7)
        assert len(br.draw(conn, P2, CFG)) == 7


def test_the_worksheet_lists_raw_attributes_and_no_counterpart(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        holdings(conn, 40)
        ids = br.draw(conn, P2, CFG)
        text = br.worksheet_text(conn, ids, P2, CFG)
    assert text.count("\n| ") == 30 + 1                                              # header row plus one row per holding
    assert "seed 1" in text and "No counterpart is listed or suggested." in text
    assert all(f"| {i} |" in text for i in ids)
    header = next(l for l in text.splitlines() if l.startswith("| holding_id"))
    assert "ounterpart" not in header and "normalized" not in header.lower()      # raw columns only


def test_record_validates_and_writes_only_the_pending_file(migrated_db, tmp_path):
    pend = tmp_path / "pending.json"
    with psycopg.connect(migrated_db) as conn:
        ids = holdings(conn, 20)
        d = br.draw(conn, P2, CFG)
        other_bdc = next(i for i in ids[:20] if conn.execute("SELECT bdc_cik FROM normalized_holdings WHERE holding_id = %s", (i,)).fetchone()[0]
                         != conn.execute("SELECT bdc_cik FROM normalized_holdings WHERE holding_id = %s", (d[0],)).fetchone()[0])
        same_bdc = next(i for i in ids[:20] if i != d[0] and conn.execute("SELECT bdc_cik FROM normalized_holdings WHERE holding_id = %s", (i,)).fetchone()[0]
                        == conn.execute("SELECT bdc_cik FROM normalized_holdings WHERE holding_id = %s", (d[0],)).fetchone()[0])
        with pytest.raises(SystemExit, match="not in the draw"):
            br.record(conn, P2, CFG, ids[-1], other_bdc, pend)
        with pytest.raises(SystemExit, match="different BDC"):
            br.record(conn, P2, CFG, d[0], same_bdc, pend)
        with pytest.raises(SystemExit, match="not in the measured period"):
            br.record(conn, P2, CFG, d[0], ids[-1], pend)
        br.record(conn, P2, CFG, d[0], other_bdc, pend)
        with pytest.raises(SystemExit, match="already has"):
            br.record(conn, P2, CFG, d[0], other_bdc, pend)
        assert conn.execute("SELECT count(*) FROM blocking_recall_checks").fetchone()[0] == 0
    assert json.loads(pend.read_text()) == [{"holding_id": d[0], "counterpart_holding_id": other_bdc}]


def test_finalize_applies_the_predicate_and_refuses_twice_or_with_nothing(migrated_db, tmp_path):
    pend = tmp_path / "pending.json"
    with psycopg.connect(migrated_db) as conn:
        a, b, c, d = seed_normalized(conn, [
            {"bdc_cik": CIKS[0], "period_end_date": P2, "borrower_normalized": "acme", "instrument_type_norm": "FIRST_LIEN", "maturity_date": date(2030, 1, 31), "spread_bps": Decimal(500)},
            {"bdc_cik": CIKS[1], "period_end_date": P2, "borrower_normalized": "acme", "instrument_type_norm": "FIRST_LIEN", "maturity_date": date(2030, 2, 28), "spread_bps": Decimal(520)},
            {"bdc_cik": CIKS[0], "period_end_date": P2, "borrower_normalized": "zeta", "instrument_type_norm": "FIRST_LIEN", "maturity_date": date(2030, 1, 31), "spread_bps": Decimal(500)},
            {"bdc_cik": CIKS[1], "period_end_date": P2, "borrower_normalized": "zeta", "instrument_type_norm": "FIRST_LIEN", "maturity_date": date(2033, 1, 31), "spread_bps": Decimal(500)}])
        for x in (a, b, c, d):                                                       # blocking_keys as block.py would have written them
            conn.execute("INSERT INTO blocking_keys (holding_id, block_key) SELECT holding_id, '2026-06-30|FIRST_LIEN|' || borrower_normalized "
                         "FROM normalized_holdings WHERE holding_id = %s", (x,))
        with pytest.raises(SystemExit, match="no pair is recorded"):
            br.finalize(conn, CFG, pend)
        pend.write_text(json.dumps([{"holding_id": a, "counterpart_holding_id": b}, {"holding_id": c, "counterpart_holding_id": d}]))
        res = br.finalize(conn, CFG, pend)
        rows = conn.execute("SELECT holding_id, counterpart_holding_id, found_by_blocking FROM blocking_recall_checks ORDER BY check_id").fetchall()
        with pytest.raises(SystemExit, match="already has rows"):
            br.finalize(conn, CFG, pend)
    assert res == {"n": 2, "found": 1}
    assert rows == [(a, b, True), (c, d, False)]                                      # maturity 3 years apart: blocking missed it


def test_the_cli_draw_writes_the_worksheet_and_prints_counts_only(migrated_db, monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("MEASURED_PERIOD_END", "2026-06-30")
    monkeypatch.setattr(br, "WORKSHEET", tmp_path / "w.md")
    with psycopg.connect(migrated_db) as conn:
        holdings(conn, 40)
        conn.commit()
    assert br.main(["--draw"]) == 0
    out = capsys.readouterr().out
    assert "drew 30 holdings" in out and "borrower" not in out
    assert (tmp_path / "w.md").read_text().startswith("# Blocking recall worksheet, 2026-06-30")
