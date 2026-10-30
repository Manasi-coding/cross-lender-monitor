"""Currency of a principal whose unit tag is missing (HPS 2026-03-31 tags principal as a 'shares' fact).

Where a principal unit exists it decides and nothing here runs. For a row with a principal and no unit, an evidence
ladder is applied, first hit wins, and the rung is recorded in normalized_holdings.currency_source:
  (a) html_symbol     an explicit currency symbol or code in the HTML principal cell
  (b) reference_code  a reference-rate code that maps to one currency, with the mapping built only from the reference
                      period's rows that have a principal unit: codes where every row agrees and there are at least
                      MIN_CODE_ROWS rows
  (c) period_link     an exact within-BDC link to a reference-period holding (same borrower_normalized, same instrument
                      description, same maturity, same reference code, unique on both sides), inheriting its unit
  (d) unknown         otherwise: the currency is unknown and the row is excluded as CURRENCY_UNKNOWN
Which rungs are enabled for a filer is set in config.yaml (filers.<key>.currency_ladder) from the validation bar:
a rung needs agreement of at least 99% on at least 30 validation rows, fixed before the numbers were seen.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict

MIN_CODE_ROWS = 5
MIN_AGREEMENT = 0.99
MIN_VALIDATION_ROWS = 30

_RATE_CODE = re.compile(r"^\s*([A-Za-z]+)\s*\+")
# only symbols that name one currency; "kr" and the yen sign are ambiguous and are left out
SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP", "C$": "CAD", "A$": "AUD", "NZ$": "NZD", "S$": "SGD", "₩": "KRW",
           "CHF": "CHF", "DKK": "DKK", "NOK": "NOK", "SEK": "SEK"}


def rate_code(interest_rate_raw: str | None) -> str | None:
    """The reference code printed before the plus sign: 'SF + 5.00%' gives 'SF', 'S+425, 0.50% Floor' gives 'S'."""
    m = _RATE_CODE.match(interest_rate_raw or "")
    return m.group(1).upper() if m else None


def symbol_currency(symbol: str | None) -> str | None:
    return SYMBOLS.get(symbol) if symbol else None


def build_code_map(pairs, min_rows: int = MIN_CODE_ROWS) -> dict[str, str]:
    """pairs: (reference code, currency) from reference-period rows that have a principal unit. Keeps a code only if
    it has at least min_rows rows and every row names the same currency."""
    seen: dict[str, Counter] = defaultdict(Counter)
    for code, ccy in pairs:
        if code and ccy:
            seen[code][ccy] += 1
    return {c: next(iter(cnt)) for c, cnt in seen.items() if len(cnt) == 1 and sum(cnt.values()) >= min_rows}


def link_key(borrower_normalized, instrument_type_raw, maturity, code):
    return (borrower_normalized, instrument_type_raw, maturity, code)


def unique_links(current: list[tuple], reference: list[tuple]) -> dict[int, int]:
    """current and reference are (id, key) lists. Returns {current id: reference id} for keys that occur exactly once on
    each side. Every row of the BDC in each period is counted, not only the candidates."""
    cur, ref = defaultdict(list), defaultdict(list)
    for i, k in current:
        cur[k].append(i)
    for i, k in reference:
        ref[k].append(i)
    return {cur[k][0]: ref[k][0] for k in cur if len(cur[k]) == 1 and len(ref.get(k, [])) == 1}


def resolve(*, symbol: str | None, code: str | None, code_map: dict[str, str], linked_unit: str | None,
            rungs: list[str]) -> tuple[str | None, str]:
    """Returns (currency or None, currency_source). linked_unit is the unit of the unique reference-period link."""
    if "a" in rungs and symbol_currency(symbol):
        return symbol_currency(symbol), "html_symbol"
    if "b" in rungs and code in code_map:
        return code_map[code], "reference_code"
    if "c" in rungs and linked_unit:
        return linked_unit.strip().upper().removeprefix("U_"), "period_link"
    return None, "unknown"
