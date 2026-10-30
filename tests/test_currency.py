"""The currency evidence ladder (pipeline/currency.py) and CURRENCY_UNKNOWN in normalize. Offline.

Validation bar, fixed before the numbers were seen: a rung is used only with agreement of at least 99% on at least 30
validation rows. Result on 2026-06-30 HPS and the ADS and ORCIC quarters: (a) 12 rows, below 30, not used; (b) 612 of
612, used; (c) 847 of 877 (96.6%), not used. config.yaml enables only rung (b)."""
import copy
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg

from pipeline import currency as C
from pipeline import normalize
from pipeline.config import load_config
from pipeline.html_schedule import parse_main_schedule
from pipeline.normalize import normalize_row

CFGS = load_config()
HPS = CFGS["filers"]["hps"]
Q1, Q2 = date(2026, 3, 31), date(2026, 6, 30)


# ------------------------------------------------------------------ helpers
def test_rate_code():
    assert C.rate_code("SF + 5.38% (incl 2.88% PIK)") == "SF"
    assert C.rate_code("E + 4.75%") == "E"
    assert C.rate_code("S+425, 0.50% Floor") == "S"
    assert C.rate_code("13.00% PIK") is None and C.rate_code(None) is None


def test_code_map_needs_5_rows_and_unanimity():
    pairs = [("SF", "USD")] * 6 + [("E", "EUR")] * 5 + [("C", "CAD")] * 4 + [("X", "USD")] * 5 + [("X", "EUR")] + [(None, "USD")] * 9
    assert C.build_code_map(pairs) == {"SF": "USD", "E": "EUR"}       # C has 4 rows, X disagrees, None is no code


def test_unique_links_need_a_single_row_on_each_side():
    cur = [(1, "a"), (2, "b"), (3, "b"), (4, "c"), (5, "d")]
    ref = [(10, "a"), (11, "b"), (12, "c"), (13, "c")]
    assert C.unique_links(cur, ref) == {1: 10}                         # b twice on the current side, c twice on the reference, d absent


# ------------------------------------------------------------------ the rungs
def test_rung_a_symbol_in_the_html_principal_cell(tmp_path):
    html = """<html><body><table><tr><td>Company(1)</td><td>Ref. Rate</td></tr>
    <tr><td>Meralm Bidco AB (4)</td><td>ST +</td><td>6.25% (incl 2.25% PIK)</td><td>8.28</td><td>%</td><td>8/29/2031</td>
        <td>SEK</td><td>427,755</td><td>41,271</td><td>40,079</td></tr>
    <tr><td>Acme Corp (4)</td><td>SF +</td><td>5.00%</td><td>9.00</td><td>%</td><td>1/1/2030</td>
        <td>$</td><td>10,000</td><td>$</td><td>9,900</td><td>$</td><td>9,800</td></tr>
    <tr><td>Plain Corp (4)</td><td>SF +</td><td>5.00%</td><td>9.00</td><td>%</td><td>1/1/2030</td>
        <td>10,000</td><td>9,900</td><td>9,800</td></tr></table></body></html>"""
    p = tmp_path / "t.htm"
    p.write_text(html, encoding="utf-8")
    rows = parse_main_schedule(p, 3, False)
    assert [r.principal_symbol for r in rows] == ["SEK", "$", None]
    assert [str(r.principal) for r in rows] == ["427755", "10000", "10000"]
    assert C.symbol_currency("SEK") == "SEK" and C.symbol_currency("$") == "USD" and C.symbol_currency("kr") is None
    assert C.resolve(symbol="SEK", code=None, code_map={}, linked_unit=None, rungs=["a"]) == ("SEK", "html_symbol")


def test_rung_b_reference_code():
    cmap = {"SF": "USD", "E": "EUR"}
    assert C.resolve(symbol=None, code="E", code_map=cmap, linked_unit=None, rungs=["b"]) == ("EUR", "reference_code")
    assert C.resolve(symbol=None, code="ST", code_map=cmap, linked_unit=None, rungs=["b"]) == (None, "unknown")   # not in the map
    assert C.resolve(symbol=None, code=None, code_map=cmap, linked_unit=None, rungs=["b"]) == (None, "unknown")    # fixed rate, no code


def test_rung_c_period_link_inherits_the_unit():
    assert C.resolve(symbol=None, code=None, code_map={}, linked_unit="U_GBP", rungs=["c"]) == ("GBP", "period_link")
    assert C.resolve(symbol=None, code=None, code_map={}, linked_unit="eur", rungs=["c"]) == ("EUR", "period_link")


def test_first_hit_wins_and_a_disabled_rung_is_skipped():
    args = dict(symbol="SEK", code="E", code_map={"E": "EUR"}, linked_unit="usd")
    assert C.resolve(**args, rungs=["a", "b", "c"]) == ("SEK", "html_symbol")
    assert C.resolve(**args, rungs=["b", "c"]) == ("EUR", "reference_code")
    assert C.resolve(**args, rungs=["c"]) == ("USD", "period_link")
    assert C.resolve(**args, rungs=[]) == (None, "unknown")
    assert HPS["currency_ladder"]["rungs"] == ["b"]                    # the configured set follows the validation bar


# ------------------------------------------------------------------ CURRENCY_UNKNOWN in normalize
def raw(unit, principal="1000000", rate="SF + 5.00%", **kw):
    r = {"holding_id": 1, "cik": HPS["cik"], "period_end_date": "2026-03-31", "portfolio_company_raw": "Acme Corp", "industry_raw": None,
         "instrument_type_raw": "First Lien Debt", "interest_rate_raw": rate, "maturity_date_raw": "1/1/2030", "principal_raw": principal,
         "principal_unit_raw": unit, "cost_raw": "990000", "fair_value_raw": "985000", "footnotes_raw": None, "source_url": "u"}
    r.update(kw)
    return r


def norm(unit, override=None, **kw):
    return normalize_row(raw(unit, **kw), "hps", HPS, CFGS, ccy_override=override)


def test_no_unit_and_no_evidence_is_currency_unknown_not_non_usd():
    n = norm(None)
    assert (n["principal_currency"], n["currency_source"], n["excluded_reason"], n["fair_value_pct_par"]) == (None, "unknown", "CURRENCY_UNKNOWN", None)


def test_a_resolved_usd_row_gets_a_percent_of_par_and_a_resolved_foreign_row_is_non_usd():
    usd = norm(None, ("USD", "reference_code"))
    assert (usd["currency_source"], usd["excluded_reason"], usd["fair_value_pct_par"]) == ("reference_code", None, Decimal("98.5"))
    eur = norm(None, ("EUR", "reference_code"))
    assert (eur["principal_currency"], eur["excluded_reason"], eur["fair_value_pct_par"]) == ("EUR", "NON_USD_PRINCIPAL", None)


def test_the_unit_still_decides_and_leaves_no_source():
    for unit, reason in (("usd", None), ("eur", "NON_USD_PRINCIPAL")):
        n = norm(unit, ("USD", "reference_code"))                      # an override is ignored when the unit exists
        assert (n["currency_source"], n["excluded_reason"]) == (None, reason)


def test_the_precedence_slot_is_unchanged():
    assert norm(None, principal=None)["excluded_reason"] == "ZERO_OR_NULL_PRINCIPAL"           # before the currency slot
    assert norm(None, instrument_type_raw="Equity Investments")["excluded_reason"] == "EQUITY_POSITION"
    assert norm(None, footnotes_raw="This is an unfunded loan commitment.")["excluded_reason"] == "UNFUNDED_COMMITMENT"
    assert norm(None, fair_value_raw=None)["excluded_reason"] == "CURRENCY_UNKNOWN"             # the currency slot is before null fair value
    assert CFGS["normalization"]["excluded_reason_order"] == ["EQUITY_POSITION", "ZERO_OR_NULL_PRINCIPAL", "UNFUNDED_COMMITMENT", "NON_USD_PRINCIPAL", "CURRENCY_UNKNOWN", "NULL_FAIR_VALUE"]


# ------------------------------------------------------------------ the ladder through normalize.run, on a scratch database
def seed(conn, period, rows):
    """rows: (name, rate, unit, instrument, maturity). Returns holding ids."""
    fid = conn.execute(
        "INSERT INTO raw_filings (cik, bdc_name, form_type, period_end_date, filing_date, accession_number, source_url) "
        "VALUES (%s, 'HPS', '10-Q', %s, %s, %s, 'u') RETURNING filing_id", (HPS["cik"], period, date(2026, 8, 1), f"acc-{period}")).fetchone()[0]
    ids = []
    for i, (name, rate, unit, inst, mat) in enumerate(rows):
        ids.append(conn.execute(
            "INSERT INTO raw_holdings (filing_id, portfolio_company_raw, instrument_type_raw, interest_rate_raw, maturity_date_raw, "
            "principal_raw, principal_unit_raw, cost_raw, fair_value_raw, row_order, source_url) "
            "VALUES (%s, %s, %s, %s, %s, '1000000', %s, '990000', '985000', %s, 'u') RETURNING holding_id",
            (fid, name, inst, rate, mat, unit, i)).fetchone()[0])
    return ids


def test_ladder_through_run_rungs_b_and_unknown_and_q2_untouched(migrated_db):
    ref = [(f"sf{i} corp", "SF + 5.00%", "usd", "First Lien Debt", "1/1/2030") for i in range(6)] + \
          [(f"eu{i} corp", "E + 4.00%", "eur", "First Lien Debt", "1/1/2030") for i in range(5)] + \
          [(f"ab{i} corp", "N + 4.00%", "nok", "First Lien Debt", "1/1/2030") for i in range(2)]      # N has 2 rows: not mapped
    cur = [("new sf corp", "SF + 5.00%", None, "First Lien Debt", "1/1/2030"),
           ("new eur corp", "E + 4.00%", None, "First Lien Debt", "1/1/2030"),
           ("new nok corp", "N + 4.00%", None, "First Lien Debt", "1/1/2030"),
           ("new fixed corp", "12.00% PIK", None, "First Lien Debt", "1/1/2030"),
           ("has unit corp", "E + 4.00%", "usd", "First Lien Debt", "1/1/2030")]
    with psycopg.connect(migrated_db) as conn:
        seed(conn, Q2, ref)
        normalize.run(conn, Q2, CFGS, verbose=False)
        before_q2 = conn.execute("SELECT * FROM normalized_holdings ORDER BY holding_id").fetchall()
        ids = seed(conn, Q1, cur)
        normalize.run(conn, Q1, CFGS, verbose=False)
        got = {r[0]: r[1:] for r in conn.execute(
            "SELECT holding_id, principal_currency, currency_source, excluded_reason, fair_value_pct_par FROM normalized_holdings WHERE period_end_date = %s", (Q1,))}
        normalize.run(conn, Q2, CFGS, verbose=False)
        after_q2 = conn.execute("SELECT * FROM normalized_holdings WHERE period_end_date = %s ORDER BY holding_id", (Q2,)).fetchall()
    assert got[ids[0]][:3] == ("USD", "reference_code", None) and got[ids[0]][3] == Decimal("98.5")
    assert got[ids[1]][:3] == ("EUR", "reference_code", "NON_USD_PRINCIPAL") and got[ids[1]][3] is None
    assert got[ids[2]][:3] == (None, "unknown", "CURRENCY_UNKNOWN")                 # code N is below 5 rows, so it is not mapped
    assert got[ids[3]][:3] == (None, "unknown", "CURRENCY_UNKNOWN")                 # a fixed rate carries no code
    assert got[ids[4]][:3] == ("USD", None, None)                                   # the unit decides, no source recorded
    assert before_q2 == after_q2 and all(r[-1] is None for r in after_q2)           # reference period: nothing changes, no source


def test_ladder_rung_c_through_run_links_only_unique_rows(migrated_db):
    cfg = copy.deepcopy(CFGS)
    cfg["filers"]["hps"]["currency_ladder"]["rungs"] = ["c"]
    ref = [("Alpha Corp", "E + 4.00%", "eur", "First Lien Debt", "1/1/2030"),
           ("Beta Corp", "SF + 5.00%", "usd", "First Lien Debt", "1/1/2030"), ("Beta Corp", "SF + 5.00%", "usd", "First Lien Debt", "1/1/2030"),
           ("Gamma Corp", "SF + 5.00%", "gbp", "First Lien Debt", "1/1/2030")]
    cur = [("Alpha Corp", "E + 4.00%", None, "First Lien Debt", "1/1/2030"),       # one on each side: linked
           ("Beta Corp", "SF + 5.00%", None, "First Lien Debt", "1/1/2030"),        # two on the reference side: not linked
           ("Gamma Corp", "SF + 5.00%", None, "First Lien Debt", "2/1/2030"),       # other maturity: not linked
           ("Delta Corp", "SF + 5.00%", None, "First Lien Debt", "1/1/2030")]       # absent from the reference
    with psycopg.connect(migrated_db) as conn:
        seed(conn, Q2, ref)
        normalize.run(conn, Q2, cfg, verbose=False)
        ids = seed(conn, Q1, cur)
        normalize.run(conn, Q1, cfg, verbose=False)
        got = {r[0]: r[1:] for r in conn.execute("SELECT holding_id, principal_currency, currency_source, excluded_reason FROM normalized_holdings WHERE period_end_date = %s", (Q1,))}
    assert got[ids[0]] == ("EUR", "period_link", "NON_USD_PRINCIPAL")
    assert [got[i] for i in ids[1:]] == [(None, "unknown", "CURRENCY_UNKNOWN")] * 3
