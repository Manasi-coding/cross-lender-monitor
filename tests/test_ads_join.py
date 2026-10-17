"""The ADS join between the printed table rows and the XBRL rows (AdsAdapter.join_html), and the table's amount cells."""
from decimal import Decimal

from pipeline.adapters import AdsAdapter
from pipeline.config import load_config
from pipeline.html_schedule import AdsHtmlRow, _ads_amount

CFG = load_config()["filers"]["ads"]


def x(ident, principal, cost, fv):
    return {"identifier": ident, "raw_name": ident, "principal": principal, "cost": cost, "fair_value": fv}


def h(order, legal, principal, cost, fv, group="G", industry="Software", cells=3):
    return AdsHtmlRow(order=order, industry=industry, group=group, legal_name=legal, type_text="First Lien Secured Debt - Term Loan",
                      rate_text=None, maturity=None, principal=principal, cost=cost, fair_value=fv, amount_cells=cells)


def test_amount_cells_read_currency_prefixes_share_counts_and_dashes():
    assert _ads_amount("Skr 614,359") == (True, Decimal(614359))
    assert _ads_amount("$") == (False, None) or _ads_amount("$")[1] is None
    assert _ads_amount("82,735 Shares") == (True, Decimal(82735))
    assert _ads_amount("(1,100)") == (True, Decimal(-1100))
    assert _ads_amount("—") == (True, None)
    assert _ads_amount("S+425, 0.50% Floor")[0] is False and _ads_amount("10/2030")[0] is False


def test_strict_join_matches_in_thousands_and_a_dash_is_empty_on_both_sides():
    a = AdsAdapter(CFG)
    schedule = [x("Software G Acme Term", Decimal(5000000), Decimal(4900000), Decimal(4800000)),
                x("Software G Acme Rev", None, Decimal(-3000), Decimal(-5000))]
    found = a.join_html(schedule, [h(0, "Acme Inc", Decimal(5000), Decimal(4900), Decimal(4800)),
                                   h(1, "Acme Inc", None, Decimal(-3), Decimal(-5))])
    assert {k: v.order for k, v in found.items()} == {"Software G Acme Term": 0, "Software G Acme Rev": 1}
    assert a.stats["html_join_strict"] == 2 and a.stats["xbrl_rows_without_html_row"] == 0


def test_relaxed_join_ignores_a_share_count_in_the_par_column():
    a = AdsAdapter(CFG)
    schedule = [x("Software G Equity", None, Decimal(101000), Decimal(117000))]
    found = a.join_html(schedule, [h(0, "Acme LP", Decimal(82735), Decimal(101), Decimal(117))])
    assert list(found) == ["Software G Equity"] and a.stats["html_join_relaxed"] == 1


def test_identical_amounts_are_told_apart_by_the_industry_group_and_legal_name():
    a = AdsAdapter(CFG)
    schedule = [x("Software G Alpha LLC", Decimal(1000000), Decimal(1000000), Decimal(1000000)),
                x("Software G Beta LLC", Decimal(1000000), Decimal(1000000), Decimal(1000000))]
    found = a.join_html(schedule, [h(0, "Beta LLC", Decimal(1000), Decimal(1000), Decimal(1000)),
                                   h(1, "Alpha LLC", Decimal(1000), Decimal(1000), Decimal(1000))])
    assert found["Software G Beta LLC"].legal_name == "Beta LLC" and found["Software G Alpha LLC"].legal_name == "Alpha LLC"
    assert a.stats["html_join_strict_resolved_by_name"] == 1      # the second table row has one XBRL row left, so no tie


def test_an_xbrl_row_with_no_table_row_stays_unmatched_and_is_counted():
    a = AdsAdapter(CFG)
    schedule = [x("Software G Lonely", Decimal(7000000), Decimal(6900000), Decimal(6800000))]
    assert a.join_html(schedule, [h(0, "Other", Decimal(1), Decimal(1), Decimal(1))]) == {}
    assert a.stats["xbrl_rows_without_html_row"] == 1
