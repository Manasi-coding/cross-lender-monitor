"""The HPS 2026-03-31 join (adapters.HtmlAssistedAdapter._join_without_principal). In that filing 729 principal amounts
are tagged as 'shares' facts, so 699 of 832 XBRL schedule rows have no principal fact and the strict
(principal, cost, fair value) join matches only 152 of 815 table rows. The second pass joins on (cost, fair value)
and takes the principal from the table cell. Offline: fixtures/hps_q1_excerpt.htm is a real excerpt of that filing.

Excerpt content (HTML table rows 9): 1 row the strict join matches, 4 rows only the second pass joins, 2 table rows that
share one (cost, fair value) key with 2 XBRL rows (ambiguous), 2 table rows with no XBRL row."""
import logging
from datetime import date
from pathlib import Path

import pytest

from pipeline.adapters import Filing, make_adapter
from pipeline.config import load_config
from pipeline.normalize import normalize_row

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
CFGS = load_config()
CFG = CFGS["filers"]["hps"]


def parse(fixture: str, period: date):
    adapter = make_adapter("hps", CFG)
    rows = adapter.parse(Filing("hps", CFG["cik"], "HPS", period, FIXTURES / fixture, "https://example.test/q1", "acc"))
    return rows, adapter.stats


@pytest.fixture(scope="module")
def q1():
    return parse("hps_q1_excerpt.htm", date(2026, 3, 31))


def by_name(rows, fragment):
    return [r for r in rows if fragment in r[0]]


def test_the_strict_join_alone_would_miss_most_rows_so_the_second_pass_runs(q1):
    _rows, stats = q1
    assert stats["html_rows"] == 9 and stats["html_unmatched"] == 8       # strict joined 1 of 9
    assert stats["relaxed_join_applied"] == 1 and CFG["html"]["relaxed_join_below_strict_share"] == 0.95


def test_joined_rows_take_principal_from_the_table_cell_and_have_no_unit(q1):
    rows, stats = q1
    cadence = by_name(rows, "Cadence - Southwick")
    assert [(r[5], r[6]) for r in cadence] == [("40488000", None), ("3042000", None)]    # table cell thousands times 1000, no unit
    assert [(r[7], r[8]) for r in cadence] == [("39857000", "40488000"), ("3007000", "3042000")]   # cost and fair value stay the XBRL facts
    assert stats["relaxed_joined"] == 4 and stats["principal_from_table_cell"] == 4
    assert cadence[0][4] == "5/3/2029"                                    # maturity still comes from the table


def test_a_row_the_strict_join_matched_keeps_its_xbrl_principal_and_unit(q1):
    rows, _ = q1
    first = by_name(rows, "Arcfield Acquisition Corp")[0]
    assert (first[5], first[6]) == ("88682000", "usd")


def test_rows_stay_in_table_order(q1):
    rows, _ = q1
    assert [r[10] for r in rows] == [1, 2, 3, 4, 5]
    assert [r[0] for r in rows][:2] == ["Arcfield Acquisition Corp"] * 2


def test_an_ambiguous_row_is_left_unjoined_and_logged_never_guessed(caplog):
    with caplog.at_level(logging.WARNING, logger="pipeline.adapters"):
        rows, stats = parse("hps_q1_excerpt.htm", date(2026, 3, 31))
    assert by_name(rows, "Kpler") == []                                   # 2 table rows, 2 XBRL candidates, same key
    assert stats["relaxed_ambiguous"] == 2
    assert sum("ambiguous join" in m and "Kpler Finance SA" in m for m in caplog.messages) == 2


def test_a_table_row_with_no_xbrl_row_is_left_unjoined_and_logged(caplog):
    with caplog.at_level(logging.WARNING, logger="pipeline.adapters"):
        rows, stats = parse("hps_q1_excerpt.htm", date(2026, 3, 31))
    assert by_name(rows, "Sedgwick") == [] and by_name(rows, "Einstein") == []
    assert stats["relaxed_no_candidate"] == 2 and stats["html_rows_unjoined"] == 4      # 2 ambiguous + 2 with no candidate
    assert any("no xbrl row" in m and "Sedgwick" in m for m in caplog.messages)
    assert stats["matched"] == len(rows) == 5


def test_the_second_period_excerpt_never_runs_the_second_pass():
    rows, stats = parse("hps_excerpt.htm", date(2026, 6, 30))
    assert stats.get("relaxed_join_applied", 0) == 0 and stats.get("relaxed_joined", 0) == 0
    assert all(r[5] is None or r[6] is not None for r in rows)            # every principal still carries its XBRL unit


def test_a_second_pass_row_without_currency_evidence_is_currency_unknown_not_non_usd(q1):
    rows, _ = q1
    r = by_name(rows, "Cadence - Southwick")[0]
    raw = {"holding_id": 1, "cik": CFG["cik"], "period_end_date": "2026-03-31", "portfolio_company_raw": r[0], "industry_raw": r[1],
           "instrument_type_raw": r[2], "interest_rate_raw": r[3], "maturity_date_raw": r[4], "principal_raw": r[5],
           "principal_unit_raw": r[6], "cost_raw": r[7], "fair_value_raw": r[8], "footnotes_raw": None, "source_url": r[11]}
    n = normalize_row(raw, "hps", CFG, CFGS)
    assert (n["principal_currency"], n["currency_source"], n["excluded_reason"], n["fair_value_pct_par"]) == (None, "unknown", "CURRENCY_UNKNOWN", None)
    assert str(n["principal"]) == "40488000"
