"""SPEC test 7: one trimmed real excerpt per filer format, and the fields normalization needs.

The excerpts in fixtures/ are real XBRL facts, footnotes and (for HPS and ORCIC) table rows cut out of
the 2026-06-30 filings by fixtures/make_excerpts.py. The adapters run on them without a database or
network. Expected values were read off the filings (see docs/day1_notes.md and docs/day2_notes.md).
"""
import re
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from pipeline.adapters import Filing, _key, make_adapter
from pipeline.html_schedule import parse_main_schedule
from pipeline.config import load_config

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
FILERS = load_config()["filers"]
URL = "https://example.test/filing.htm"

# raw_holdings tuple positions
NAME, INDUSTRY, TYPE, RATE, MATURITY, PRINCIPAL, UNIT, COST, FV, FOOTNOTES, ORDER, SOURCE = range(12)


def parse(key: str, fixture: str, period: date = date(2026, 6, 30)):
    cfg = FILERS[key]
    adapter = make_adapter(key, cfg)
    rows = adapter.parse(Filing(cfg["fixture_label"], cfg["cik"], "x", period, FIXTURES / fixture, URL, "acc"))
    return rows, adapter.stats


def find(rows, text, n=0, **eq):
    hits = [r for r in rows if text.lower() in r[NAME].lower() and all(r[globals()[k.upper()]] == v for k, v in eq.items())]
    assert len(hits) > n, f"{text!r} {eq}: {len(hits)} hits"
    return hits[n]


def has_note(row, pattern):
    return pattern is not None and pattern.lower() in (row[FOOTNOTES] or "").lower()


@pytest.fixture(scope="module")
def ads():
    return parse("ads", "ads_excerpt.htm")


@pytest.fixture(scope="module")
def hps():
    return parse("hps", "hps_excerpt.htm")


@pytest.fixture(scope="module")
def orcic():
    return parse("orcic", "orcic_excerpt.htm")


# ---------------------------------------------------------------- every filer
@pytest.mark.parametrize("fixture,key", [("ads", "ads"), ("hps", "hps"), ("orcic", "orcic")])
def test_every_row_carries_source_url_and_row_order(fixture, key):
    rows, _ = parse(key, f"{fixture}_excerpt.htm")
    assert 0 < len(rows) <= 30
    assert all(r[SOURCE] == URL for r in rows)
    assert [r[ORDER] for r in rows] == list(range(1, len(rows) + 1))


@pytest.mark.parametrize("key,fixture", [("ads", "ads_excerpt.htm"), ("hps", "hps_excerpt.htm"), ("orcic", "orcic_excerpt.htm")])
def test_numbers_are_plain_decimal_text_with_no_exponent(key, fixture):
    rows, _ = parse(key, fixture)
    for r in rows:
        for v in (r[PRINCIPAL], r[COST], r[FV]):
            assert v is None or ("e" not in v.lower() and float(v) == float(v))


# ---------------------------------------------------------------- ADS
def test_ads_typed_row_fields(ads):
    rows, _ = ads
    r = find(rows, "Corpuls", type="First Lien Secured Debt - Term Loan")
    assert (r[RATE], r[MATURITY], r[PRINCIPAL], r[UNIT], r[COST], r[FV]) == (
        "E+650, 0.50% Floor", "06/28/2030", "20000000", "U_EUR", "21548000", "22706000")


def test_ads_mixed_currency_tranches_keep_their_own_principal_unit(ads):
    rows, _ = ads
    nars = [r for r in rows if "North American Rail" in r[NAME] and r[PRINCIPAL]]
    assert {r[UNIT] for r in nars} == {"U_CAD", "U_USD"}


def test_ads_unfunded_row_has_no_principal_and_negative_marks(ads):
    rows, _ = ads
    r = find(rows, "North American Rail", type="First Lien Secured Debt – Delayed Draw", principal=None)
    assert (r[UNIT], r[COST], r[FV]) == (None, "-8000", "-63000")


def test_ads_missing_fair_value_stays_null_never_zero(ads):
    rows, _ = ads
    r = find(rows, "SK Neptune Husky")
    assert (r[PRINCIPAL], r[COST], r[FV]) == ("9588000", "9396000", None)


def test_ads_share_count_sits_in_the_principal_field_with_a_usd_unit(ads):
    rows, _ = ads
    r = find(rows, "DCA Investment Holding", type="Common Equity - Stock")
    assert (r[PRINCIPAL], r[UNIT], r[MATURITY]) == ("82735000", "U_USD", None)


def test_ads_identifier_without_investment_type_token_is_parsed_from_the_name_piece(ads):
    rows, stats = ads
    r = find(rows, "Virgin Media Secured")
    assert r[TYPE] == "First Lien Secured Debt - Corporate Bond"
    assert (r[RATE], r[MATURITY]) == ("5.50%", "05/15/2029")
    assert r[NAME].endswith("PLC,")          # raw name keeps its trailing comma
    assert stats["no_investment_type_token"] == 10 and stats["fallback_name_piece_type"] == 10


def test_ads_rate_printed_straight_after_the_type_is_split_off(ads):
    rows, _ = ads
    r = find(rows, "G2CI Evergreen", type="First Lien Secured Debt - Revolver")
    assert r[RATE] == "S+475, 0.75% Floor"


def test_ads_token_glued_to_the_name_is_still_found(ads):
    rows, stats = ads
    r = find(rows, "Trading Technologies International")
    assert r[NAME].endswith("Trading Technologies International, Inc.")
    assert r[TYPE] == "First Lien Secured Debt – Term Loan"
    assert stats["token_glued_to_name"] == 1


def test_ads_equity_without_rate_or_maturity_gets_no_invented_values(ads):
    rows, _ = ads
    r = find(rows, "Valor VCI Intermediate Topco 1")
    assert (r[TYPE], r[RATE], r[MATURITY], r[PRINCIPAL]) == ("Common Equity - Membership Interest", None, None, None)


def test_ads_maturity_falls_back_to_the_xbrl_text_fact(ads):
    rows, stats = ads
    r = find(rows, "ERC Topco", type="First Lien Secured Debt - Revolver")
    assert r[MATURITY] == "03/29/2030"
    assert stats["fallback_xbrl_text_fact_maturity"] == 1


def test_ads_trailing_text_after_the_maturity_is_kept_as_printed(ads):
    rows, _ = ads
    assert find(rows, "M-Files", maturity="11/27/2031 One")


def test_ads_non_accrual_footnote_matches_the_configured_pattern(ads):
    rows, _ = ads
    pattern = FILERS["ads"]["non_accrual_pattern"]
    flagged = [r for r in rows if has_note(r, pattern)]
    assert len(flagged) == 5
    assert any("SK Neptune" in r[NAME] for r in flagged)
    assert not has_note(find(rows, "Corpuls", type="First Lien Secured Debt - Term Loan"), pattern)


def test_ads_industry_comes_from_the_identifier_prefix_and_the_printed_totals(ads):
    rows, stats = ads
    assert find(rows, "Corpuls", type="First Lien Secured Debt - Term Loan")[INDUSTRY] == "Health Care Equipment & Supplies"
    assert find(rows, "North American Rail", type="First Lien Secured Debt – Term Loan", unit="U_CAD")[INDUSTRY] == "Transportation Infrastructure"
    assert find(rows, "Esdec")[INDUSTRY] == "Building Products"
    assert stats["industry_by_prefix"] == 26 and stats["industry_none"] == 0


def test_ads_industry_alias_map_covers_the_two_prefixes_the_table_does_not_print(ads):
    rows, stats = ads
    assert find(rows, "IW Buyer")[INDUSTRY] == "Electrical Equipment"       # identifier says 'Electric Equipment'
    assert find(rows, "KDC/ONE")[INDUSTRY] == "Personal Care Products"      # identifier starts with 'Heat Makes Sense'
    assert stats["industry_by_alias"] == 2
    assert FILERS["ads"]["industry_aliases"] == {"Electric Equipment": "Electrical Equipment",
                                                 "Heat Makes Sense": "Personal Care Products"}


def test_ads_has_no_unfunded_pattern_and_no_row_carries_one(ads):
    rows, _ = ads
    assert FILERS["ads"]["unfunded_pattern"] is None
    assert not any("unfunded" in (r[FOOTNOTES] or "").lower() for r in rows)


# ---------------------------------------------------------------- HPS
def test_hps_row_fields_come_from_xbrl_numbers_and_the_printed_table(hps):
    rows, _ = hps
    r = find(rows, "Arcfield Acquisition Corp", cost="82154000")
    assert (r[NAME], r[INDUSTRY], r[TYPE], r[RATE], r[MATURITY]) == (
        "Arcfield Acquisition Corp", "Aerospace & Defense", "First Lien Debt", "SF + 5.00%", "10/28/2031")
    assert (r[PRINCIPAL], r[UNIT], r[COST], r[FV]) == ("82330000", "usd", "82154000", "82092000")


def test_hps_name_has_no_xbrl_index_and_no_footnote_markers(hps):
    rows, _ = hps
    assert not [r[NAME] for r in rows if re.search(r"\(\d{1,3}\)", r[NAME])]
    assert find(rows, "Cadence - Southwick")[NAME] == "Cadence - Southwick, Inc."      # XBRL says 'Cadence - Southwick, Inc. 1'


def test_hps_typing_stays_by_lien_class(hps):
    rows, _ = hps
    assert {r[TYPE] for r in rows} == {"First Lien Debt", "Other Secured Debt", "Equity Investments",
                                       "Investments in Joint Ventures"}
    # a revolver or delayed draw commitment is not told apart from a term loan
    assert find(rows, "Oak Funding", cost="-187000")[TYPE] == "First Lien Debt"


def test_hps_pik_text_is_kept_in_the_rate_string(hps):
    rows, _ = hps
    assert find(rows, "Titan BW", principal="233251000")[RATE] == "SF + 5.38% (incl 2.88% PIK)"


def test_hps_unfunded_pattern_flags_the_footnote_rows_and_only_those(hps):
    rows, _ = hps
    pattern = FILERS["hps"]["unfunded_pattern"]
    assert pattern == "unfunded loan commitment"
    flagged = [r for r in rows if has_note(r, pattern)]
    assert len(flagged) == 8
    assert has_note(find(rows, "Arcfield Acquisition Corp", cost="-33000"), pattern)
    assert not has_note(find(rows, "Arcfield Acquisition Corp", cost="82154000"), pattern)
    # the partly funded rows (positive cost and fair value) carry the footnote too
    assert has_note(find(rows, "Cadence - Southwick", cost="11553000"), pattern)


def test_hps_non_usd_principal_units_are_kept(hps):
    rows, _ = hps
    assert find(rows, "Netrisk", cost="37875000")[UNIT] == "eur"
    assert find(rows, "Aryeh Bidco")[UNIT] == "cad"


def test_hps_equity_rows_have_no_maturity_or_principal_and_keep_their_xbrl_zeros(hps):
    rows, _ = hps
    r = find(rows, "Thrasio Holdings")
    assert (r[TYPE], r[MATURITY], r[PRINCIPAL], r[COST], r[FV]) == ("Equity Investments", None, None, "0", "0")


def test_hps_ultra_iii_xbrl_row_without_a_main_schedule_row_is_dropped(hps):
    rows, stats = hps
    assert stats["xbrl_dropped_no_main_schedule_row"] == 1 and stats["xbrl_dropped_funded"] == 1
    assert not any("Sentinel Buyer" in r[NAME] for r in rows)
    assert find(rows, "ULTRA III")[TYPE] == "Investments in Joint Ventures"   # the JV holding itself stays


def test_hps_identical_rows_are_both_kept(hps):
    rows, stats = hps
    assert len([r for r in rows if "Kpler" in r[NAME]]) == 2
    assert stats["multi_resolved_by_name"] >= 1 and stats["matched"] == stats["html_rows"] == len(rows)


def test_hps_non_accrual_footnote_matches_the_configured_pattern(hps):
    rows, _ = hps
    flagged = [r for r in rows if has_note(r, FILERS["hps"]["non_accrual_pattern"])]
    assert [r[NAME] for r in flagged] == ["Enstall Group B.V."]


# ---------------------------------------------------------------- ORCIC
def test_orcic_row_fields(orcic):
    rows, _ = orcic
    r = find(rows, "DIRECTV Financing")
    assert (r[INDUSTRY], r[TYPE], r[RATE]) == ("Advertising and media", "First lien senior secured loan", "S+ 5.25%")
    assert (r[PRINCIPAL], r[UNIT], r[COST], r[FV]) == ("62670000", "usd", "62767000", "62946000")


def test_orcic_maturity_is_kept_as_printed_month_and_year(orcic):
    rows, stats = orcic
    assert find(rows, "DIRECTV Financing")[MATURITY] == "8/2029"
    assert find(rows, "Jeppesen")[MATURITY] == "10/2032"
    assert find(rows, "Coupa Holdings")[MATURITY] == "2/2030"
    assert "maturity_month_year_to_month_end" not in stats     # normalize converts M/YYYY to the month end


def test_orcic_cash_and_pik_columns(orcic):
    rows, _ = orcic
    assert find(rows, "CoolSys")[RATE] == "S+ 3.50% Cash plus 2.50% PIK"


def test_orcic_equity_rows_have_no_maturity(orcic):
    rows, _ = orcic
    for text in ("OCIC SLF", "Notorious Purchaser II", "GT Silver"):
        assert find(rows, text)[MATURITY] is None


def test_orcic_non_usd_principal_unit_is_kept(orcic):
    rows, _ = orcic
    assert find(rows, "Hg Genesis 9")[UNIT] == "eur"


def test_orcic_partially_unfunded_rows_are_not_flagged_by_any_pattern(orcic):
    rows, _ = orcic
    assert FILERS["orcic"]["unfunded_pattern"] is None
    partial = [r for r in rows if "partially unfunded" in (r[FOOTNOTES] or "").lower()]
    assert len(partial) == 4                      # present in the footnotes ...
    sts = find(rows, "STS PARENT", type="First lien senior secured revolving loan")
    assert (sts[PRINCIPAL], sts[FV]) == ("11828000", "11641000")        # ... and a normal mark at about par
    assert not has_note(find(rows, "Jeppesen"), "partially unfunded")   # one row without the footnote


def test_orcic_duplicate_fair_value_only_xbrl_row_is_dropped(orcic):
    rows, stats = orcic
    assert stats["xbrl_dropped_no_main_schedule_row"] == 1 and stats["xbrl_dropped_funded"] == 0
    assert len([r for r in rows if r[NAME] == "LSI Financing LLC"]) == 1


def test_orcic_same_amounts_different_names_are_told_apart(orcic):
    rows, stats = orcic
    assert {r[NAME] for r in rows if "Silver Co-Invest" in r[NAME]} == {"GT Silver Co-Invest SCSp", "WP Silver Co-Invest, L.P."}
    assert stats["multi_resolved_by_name"] == 1


def test_orcic_non_accrual_footnote_matches_the_configured_pattern(orcic):
    rows, _ = orcic
    assert len([r for r in rows if has_note(r, FILERS["orcic"]["non_accrual_pattern"])]) == 2


# ---------------------------------------------------------------- the join key and printed dashes
def test_a_printed_dash_is_empty_in_the_join_key_and_never_stored(hps):
    html = parse_main_schedule(FIXTURES / "hps_excerpt.htm", 3, False)
    thrasio = next(r for r in html if r.name.startswith("Thrasio"))
    assert (thrasio.cost, thrasio.fair_value) == (None, None)           # the table prints dashes
    rows, _ = hps
    stored = find(rows, "Thrasio Holdings")
    assert (stored[COST], stored[FV]) == ("0", "0")                    # the zeros are XBRL facts, not the dash


def test_join_key_treats_empty_and_zero_alike_on_both_sides_only():
    assert _key(None, Decimal(0), None) == _key(Decimal(0), None, Decimal(0)) == (0, 0, 0)
    assert _key(Decimal(82330), Decimal(82154), Decimal(82092), 1000) == (82330000, 82154000, 82092000)
