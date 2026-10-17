"""SPEC tests 1 and 2 (names), plus the type, rate, floor and date rules of normalize.py.

Tests 1 and 2 use the exact inputs and expectations of SPEC section 13. CLAUDE.md reserves the other edge
case tests (Holdings versus Holdco beyond test 1, digits in names, same-BDC collisions) for the project owner."""
from datetime import date
from decimal import Decimal

import pytest

from pipeline.config import load_config
from pipeline.normalize import (collapse_repeated_prefix, hps_floor_bps, normalize_instrument, normalize_name,
                                parse_maturity, parse_rate, strip_industry_prefix)

CFG = load_config()


def norm(name: str) -> str:
    return normalize_name(name, CFG)[0]


# ------------------------------------------------------------------ SPEC test 1 and 2
def test_1_suffix_variants_normalize_to_a_comparable_form():
    assert norm("Acme Holdings, LLC") == norm("ACME HOLDCO INC") == "acme"


def test_2_digits_are_kept():
    assert norm("Acme Holdings 2, LLC") == "acme 2"
    assert norm("Acme Holdings 2, LLC") != norm("Acme Holdings, LLC")


# ------------------------------------------------------------------ other name rules
def test_name_folds_accents_ampersand_leading_the_and_dotted_abbreviations():
    assert norm("The Société Générale & Co. S.A.") == "societe generale and sa"
    assert norm("Mavis Tire Express Services TopCo, L.P.") == "mavis tire express services"
    assert norm("O'Brien Partners, Inc.") == "obrien partners"


def test_decimal_points_survive_in_names():
    assert norm("Fund 2.5 Holdings LLC") == "fund 2 5"


def test_a_name_that_is_all_legal_tokens_falls_back_to_the_cleaned_name():
    assert normalize_name("Holdings, LLC", CFG) == ("holdings llc", True)


def test_ads_industry_prefix_and_repeated_group_are_removed():
    raw = "Aerospace & Defense Accel International Accel International Holdings, LLC"
    stripped = collapse_repeated_prefix(strip_industry_prefix(raw, "Aerospace & Defense"))
    assert stripped == "Accel International Holdings, LLC"
    assert norm(stripped) == "accel international"
    assert strip_industry_prefix("Software Zendesk", None) == "Software Zendesk"
    assert collapse_repeated_prefix("Kaman Kaman Corp") == "Kaman Corp"
    assert collapse_repeated_prefix("Cadence - Southwick, Inc.") == "Cadence - Southwick, Inc."


# ------------------------------------------------------------------ instrument type
@pytest.mark.parametrize("raw,expected", [
    ("First Lien Secured Debt - Term Loan", "FIRST_LIEN"),
    ("First Lien Secured Debt – Delayed Draw", "DELAYED_DRAW"),      # a first lien delayed draw is DELAYED_DRAW
    ("First lien senior secured revolving loan", "REVOLVER"),
    ("Second lien senior secured loan 1", "SECOND_LIEN"),
    ("Unsecured notes", "UNSECURED"),
    ("First Lien Debt", "FIRST_LIEN"),
    ("Other Secured Debt", "OTHER"),
    ("Investments in Joint Ventures", "OTHER"),
    ("Common Equity - Stock", "EQUITY"),
    ("Series A Preferred Units", "EQUITY"),
    ("Class A-2 Units", "EQUITY"),                                    # the 2 is part of the class name, not a share count
    ("Common Equity - Limited Partnership 90,443 Units", "EQUITY"),   # the share count is stripped first
    ("LP Interest", "EQUITY"),                                        # ownership interests as ORCIC prints them
    ("LLC interest", "EQUITY"),
    ("Class A Interests", "EQUITY"),
    ("Specialty finance equity investment", "EQUITY"),
    ("Specialty finance debt investment", "OTHER"),                   # debt, so it stays OTHER
    ("Senior convertible notes", "OTHER"),
    ("Investment partnership", "OTHER"),                              # not clearly an ownership interest: left OTHER
    ("Structured Finance Investments", "OTHER"),
    (None, "OTHER"),
])
def test_instrument_type(raw, expected):
    assert normalize_instrument(raw, CFG) == expected


def test_share_count_is_stripped_before_matching_keywords():
    # "units" alone is an equity keyword, so with the count removed no keyword is left
    assert normalize_instrument("Term Loan 90,443 Units", CFG) == "OTHER"


# ------------------------------------------------------------------ rate: spread, PIK, reference code
def rate(raw):
    return parse_rate(raw, CFG)


def test_plain_spread_and_floor_from_the_ads_string():
    r = rate("S+425, 0.50% Floor")
    assert (r["reference_rate"], r["spread_bps"], r["pik_bps"], r["floor_bps"]) == ("SOFR", Decimal(425), Decimal(0), Decimal(50))


def test_percent_spread_for_hps_and_orcic():
    assert rate("SF + 5.00%")["spread_bps"] == Decimal(500)
    assert rate("S+ 5.25%")["spread_bps"] == Decimal(525)
    assert rate("E + 4.75%")["reference_rate"] == "EURIBOR"


def test_cash_plus_pik_adds_the_pik_part_in_ads_and_orcic():
    ads = rate("S+400 Cash plus 1.50% PIK, 1.00% Floor")
    assert (ads["spread_bps"], ads["pik_bps"], ads["floor_bps"], ads["pik_kind"]) == (Decimal(550), Decimal(150), Decimal(100), "cash_plus")
    orcic = rate("S+ 3.00% Cash plus 1.50% PIK")
    assert (orcic["spread_bps"], orcic["pik_bps"]) == (Decimal(450), Decimal(150))
    assert rate("S+ 2.75% Cash plus 3.25 PIK")["spread_bps"] == Decimal(600)     # ORCIC prints one PIK value without a percent sign


def test_hps_included_pik_does_not_add_again():
    r = rate("SF + 5.38% (incl 2.88% PIK)")
    assert (r["spread_bps"], r["pik_bps"], r["pik_kind"]) == (Decimal(538), Decimal(288), "included")


def test_all_pik_spread_and_fixed_rates():
    assert (rate("SF + 7.75% PIK")["spread_bps"], rate("SF + 7.75% PIK")["pik_bps"]) == (Decimal(775), Decimal(775))
    fixed = rate("13.00% PIK")
    assert (fixed["reference_rate"], fixed["spread_bps"], fixed["pik_bps"]) == ("FIXED", None, Decimal(1300))
    assert rate("N/A 12.00%")["reference_rate"] == "FIXED"
    assert rate("10.75%")["spread_bps"] is None


def test_only_the_three_codes_are_mapped_others_are_kept_as_printed():
    assert rate("SONIA+300")["reference_rate"] == "SONIA"
    assert rate("SN + 6.00% PIK")["reference_rate"] == "SN"
    assert rate("C+475, 1.00% Floor")["reference_rate"] == "C"


def test_floor_only_string_has_no_rate_and_no_code():
    r = rate("7.00% Floor")
    assert (r["reference_rate"], r["spread_bps"], r["floor_bps"]) == (None, None, Decimal(700))


def test_missing_rate_string_gives_nulls_and_zero_pik():
    r = rate(None)
    assert (r["reference_rate"], r["spread_bps"], r["floor_bps"], r["pik_bps"]) == (None, None, None, Decimal(0))


# ------------------------------------------------------------------ floor from the HPS footnotes
def test_hps_floor_comes_from_footnote_text():
    assert hps_floor_bps("x | The interest rate floor on these investments as of June 30, 2026 was 0.75%. | y") == (Decimal(75), False)
    assert hps_floor_bps("There are no interest rate floors on these investments.") == (Decimal(0), False)
    assert hps_floor_bps("Unrelated footnote.") == (None, False)
    assert hps_floor_bps(None) == (None, False)


# ------------------------------------------------------------------ maturity
def test_maturity_formats():
    assert parse_maturity("10/28/2031") == date(2031, 10, 28)
    assert parse_maturity("6/9/2031") == date(2031, 6, 9)
    assert parse_maturity("11/27/2031 One") == date(2031, 11, 27)
    assert parse_maturity("8/2029") == date(2029, 8, 31)             # M/YYYY is the month end
    assert parse_maturity("2/2028") == date(2028, 2, 29)             # leap year
    assert parse_maturity("2/2030") == date(2030, 2, 28)
    assert parse_maturity(None) is None and parse_maturity("N/A") is None
