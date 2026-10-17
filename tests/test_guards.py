"""SPEC test 11: the null, zero, currency, unfunded and equity guards on fair_value_pct_par and excluded_reason.
One reason per row, first match in the configured order."""
from decimal import Decimal

from pipeline.config import load_config
from pipeline.normalize import normalize_row, pct_par

CFG = load_config()
FILERS = CFG["filers"]
HPS_NOTE = "Position or portion thereof is an unfunded loan commitment, and no interest is being earned on the unfunded portion."
ORCIC_NOTE = "Position or portion thereof is a partially unfunded debt or equity commitment."


def row(filer="ads", **kw):
    raw = {"holding_id": 1, "cik": FILERS[filer]["cik"], "period_end_date": "2026-06-30",
           "portfolio_company_raw": "Acme Holdings, LLC", "industry_raw": None,
           "instrument_type_raw": "First Lien Secured Debt - Term Loan", "interest_rate_raw": "S+425, 0.50% Floor",
           "maturity_date_raw": "01/01/2030", "principal_raw": "1000000", "principal_unit_raw": "U_USD",
           "cost_raw": "990000", "fair_value_raw": "985000", "footnotes_raw": None, "source_url": "https://example.test"}
    raw.update(kw)
    return normalize_row(raw, filer, FILERS[filer], CFG)


def test_a_normal_row_gets_a_decimal_percent_of_par():
    r = row()
    assert r["excluded_reason"] is None
    assert r["fair_value_pct_par"] == Decimal("98.5")
    assert isinstance(r["fair_value_pct_par"], Decimal)


def test_zero_principal_gives_null_and_a_reason_and_never_divides_by_zero():
    for principal in ("0", None):
        r = row(principal_raw=principal, principal_unit_raw="U_USD" if principal else None)
        assert (r["fair_value_pct_par"], r["excluded_reason"]) == (None, "ZERO_OR_NULL_PRINCIPAL")
    assert pct_par(Decimal(100), Decimal(0)) is None and pct_par(Decimal(100), None) is None and pct_par(None, Decimal(5)) is None


def test_non_usd_principal_is_kept_but_has_no_percent_of_par():
    r = row(principal_raw="20000000", principal_unit_raw="U_EUR", cost_raw="21548000", fair_value_raw="22706000")
    assert (r["fair_value_pct_par"], r["excluded_reason"], r["principal_currency"]) == (None, "NON_USD_PRINCIPAL", "EUR")
    assert r["fair_value"] == Decimal(22706000)            # the row and its marks are kept


def test_hps_unfunded_pattern_excludes_even_with_a_positive_ratio():
    r = row("hps", footnotes_raw=HPS_NOTE, principal_raw="17561000", principal_unit_raw="usd", cost_raw="11553000", fair_value_raw="11708000")
    assert (r["fair_value_pct_par"], r["excluded_reason"]) == (None, "UNFUNDED_COMMITMENT")


def test_the_same_row_without_the_footnote_keeps_its_value():
    r = row("hps", footnotes_raw=None, principal_raw="17561000", principal_unit_raw="usd", fair_value_raw="11708000")
    assert r["excluded_reason"] is None and r["fair_value_pct_par"] is not None


def test_orcic_partially_unfunded_row_with_a_normal_ratio_keeps_its_value():
    r = row("orcic", footnotes_raw=ORCIC_NOTE, principal_raw="11828000", principal_unit_raw="usd", fair_value_raw="11641000")
    assert r["excluded_reason"] is None
    assert round(r["fair_value_pct_par"], 2) == Decimal("98.42")


def test_equity_is_excluded_first_even_with_a_principal():
    r = row(instrument_type_raw="Common Equity - Stock", principal_raw="82735000", principal_unit_raw="U_USD")
    assert (r["instrument_type_norm"], r["excluded_reason"], r["fair_value_pct_par"]) == ("EQUITY", "EQUITY_POSITION", None)


def test_reason_order_is_equity_zero_unfunded_non_usd_null_fair_value():
    # equity beats zero principal; zero principal beats unfunded; unfunded beats non-USD; non-USD beats null fair value
    assert row("hps", instrument_type_raw="Equity Investments", principal_raw=None, footnotes_raw=HPS_NOTE)["excluded_reason"] == "EQUITY_POSITION"
    assert row("hps", principal_raw="0", footnotes_raw=HPS_NOTE)["excluded_reason"] == "ZERO_OR_NULL_PRINCIPAL"
    assert row("hps", principal_raw="5", principal_unit_raw="eur", footnotes_raw=HPS_NOTE)["excluded_reason"] == "UNFUNDED_COMMITMENT"
    assert row(principal_raw="5", principal_unit_raw="U_EUR", fair_value_raw=None)["excluded_reason"] == "NON_USD_PRINCIPAL"


def test_null_fair_value_is_kept_null_and_not_turned_into_zero():
    r = row(fair_value_raw=None)
    assert (r["fair_value"], r["fair_value_pct_par"], r["excluded_reason"]) == (None, None, "NULL_FAIR_VALUE")


def test_non_accrual_flag_follows_the_filer_pattern_only():
    note = "Loan was on non-accrual status as of June 30, 2026."
    assert row("ads", footnotes_raw=note)["non_accrual"] is True
    assert row("orcic", footnotes_raw="Investment was on non-accrual status as of June 30, 2026.")["non_accrual"] is True
    assert row("ads", footnotes_raw="Some other footnote.")["non_accrual"] is False
    assert row("ads", footnotes_raw=note)["excluded_reason"] is None        # a distressed mark stays in
