"""normalize.py: raw_holdings -> normalized_holdings for the measured period (phase_wise.md 6.1).

Run: python -m pipeline.normalize
Upserts by holding_id and never truncates (labels and candidate pairs reference these rows). Refuses to run
once the matcher is frozen. Every raw row of the measured period is written; equity and OTHER rows are kept
with their own type and are never candidates (block.py).

Spread convention: spread_bps is the TOTAL spread in basis points, cash plus PIK, and pik_bps is the PIK part
(so a comparison copies spread_bps and does not add pik_bps again).
PIK phrasing, read per filer before parsing:
  ADS, ORCIC  "S+425 Cash plus 2.50% PIK"      total = cash + PIK
  HPS         "SF + 5.38% (incl 2.88% PIK)"    the stated spread already includes the PIK part
  all         "SF + 7.75% PIK", "10.00% PIK"    the whole stated rate is paid in kind
"""
from __future__ import annotations

import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal, DivisionByZero, InvalidOperation
from typing import Any

import psycopg

from pipeline.config import load_config, load_env_file, measured_period_end

# --------------------------------------------------------------------------- names
_PUNCT = re.compile(r"[^a-z0-9]+")


def fold(text: str) -> str:
    """Fold accents, lowercase, '&' becomes 'and', punctuation becomes a space. Digits stay."""
    s = unicodedata.normalize("NFKD", text)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower().replace("&", " and ")
    # periods (not decimal points) and apostrophes are removed so "L.P." becomes "lp" and "O'Brien" "obrien";
    # every other punctuation mark becomes a space
    s = re.sub(r"\.(?!\d)|['’]", "", s)
    return _PUNCT.sub(" ", s).strip()


def strip_alias_clauses(raw: str, starts: list[str]) -> str:
    """Remove each balanced parenthetical clause whose text starts with an alias word (dba, f/k/a, ...). Clauses nest
    ("(f/k/a X (f/k/a Y))" goes as one). Other parentheticals, an unclosed "(" and the text outside stay."""
    pat = re.compile(r"^\s*(?:%s)(?![A-Za-z0-9])" % "|".join(re.escape(s) for s in sorted(starts, key=len, reverse=True)), re.I)
    out, i = [], 0
    while i < len(raw):
        if raw[i] == "(":
            depth, j = 0, i
            while j < len(raw):
                depth += (raw[j] == "(") - (raw[j] == ")")
                j += 1
                if depth == 0:
                    break
            if depth == 0 and pat.match(raw[i + 1:j - 1]):
                out.append(" ")
                i = j
                continue
        out.append(raw[i])
        i += 1
    return "".join(out)


def normalize_name(raw: str, cfg: dict) -> tuple[str, bool]:
    """Returns (normalized name, used_fallback). Legal-form and structural tokens are dropped, a leading
    'the' is dropped, digits stay. dba / f/k/a clauses are removed first. An empty result falls back to the cleaned name."""
    n = cfg["normalization"]
    drop = set(n["legal_form_tokens"]) | set(n["structural_tokens"])
    cleaned = fold(strip_alias_clauses(raw or "", n.get("alias_clause_starts", [])))
    tokens = cleaned.split()
    if tokens and tokens[0] == "the":
        tokens = tokens[1:]
    kept = [t for t in tokens if t not in drop]
    if not kept:
        return cleaned, True
    return " ".join(kept), False


def strip_industry_prefix(name: str, industry: str | None) -> str:
    if industry and name.startswith(industry + " "):
        return name[len(industry) + 1:]
    return name


def collapse_repeated_prefix(name: str) -> str:
    """'Accel International Accel International Holdings, LLC' -> 'Accel International Holdings, LLC'."""
    words = name.split()
    for k in range(1, len(words) // 2 + 1):
        if [fold(w) for w in words[:k]] == [fold(w) for w in words[k:2 * k]] and any(fold(w) for w in words[:k]):
            return " ".join(words[k:])
    return name


# --------------------------------------------------------------------------- instrument type
# a share count, not the number inside a class name such as "Class A-2 Units"
_SHARE_COUNT = re.compile(r"(?<![\w-])\d[\d,]*(?:\.\d+)?\s*(?:shares?|units?)\b", re.I)


def normalize_instrument(raw: str | None, cfg: dict) -> str:
    """FIRST_LIEN, SECOND_LIEN, REVOLVER, DELAYED_DRAW, UNSECURED, OTHER, or EQUITY (own type, never a
    candidate). Share counts are stripped from the type text first."""
    n = cfg["normalization"]
    text = _SHARE_COUNT.sub(" ", raw or "").lower()
    if any(k in text for k in n["equity_keywords"]):
        return "EQUITY"
    for type_name, words in n["instrument_keywords"].items():
        if any(w in text for w in words):
            return type_name.upper()
    return "OTHER"


# --------------------------------------------------------------------------- rate
_NUM = r"(\d+(?:\.\d+)?)"
_REF_SPREAD = re.compile(rf"^\s*([A-Za-z]{{1,6}})\s*\+\s*{_NUM}\s*(%?)")
_FIXED_ANY = re.compile(rf"^\s*(?:N/A\s+)?{_NUM}\s*%")
_CASH_PLUS_PIK = re.compile(rf"Cash\s+plus\s+{_NUM}\s*%?\s*PIK", re.I)
_INCL_PIK = re.compile(rf"\(\s*incl\.?\s+{_NUM}\s*%\s*PIK\s*\)", re.I)
_PLAIN_PIK = re.compile(rf"{_NUM}\s*%\s*PIK\b", re.I)
_FLOOR = re.compile(rf"{_NUM}\s*%\s*Floor", re.I)
_EQUITY_PLUS = re.compile(rf"^\s*([A-Za-z]+)\s+plus\s+{_NUM}\s*%\s*PIK", re.I)


def _bps(value: str, percent: bool) -> Decimal:
    v = Decimal(value)
    return v * 100 if percent else v


def parse_rate(raw: str | None, cfg: dict) -> dict[str, Any]:
    """reference_rate, spread_bps (total, cash plus PIK), pik_bps, floor_bps (from the rate string only),
    and the PIK phrasing kind ('none', 'cash_plus', 'included', 'all_pik')."""
    codes = cfg["normalization"]["reference_rate_codes"]
    out: dict[str, Any] = {"reference_rate": None, "spread_bps": None, "pik_bps": Decimal(0),
                           "floor_bps": None, "pik_kind": "none", "ref_code": None}
    if not raw:
        return out
    fm = _FLOOR.search(raw)
    if fm:
        out["floor_bps"] = Decimal(fm.group(1)) * 100
    m = _REF_SPREAD.match(raw)
    if m:
        code, num, pct = m.group(1).upper(), m.group(2), bool(m.group(3))
        out["ref_code"] = code
        out["reference_rate"] = codes.get(code, code)
        stated = _bps(num, pct)
        cp, inc, plain = _CASH_PLUS_PIK.search(raw), _INCL_PIK.search(raw), _PLAIN_PIK.search(raw)
        if cp:       # cash spread plus PIK: add
            out["pik_kind"], out["pik_bps"] = "cash_plus", Decimal(cp.group(1)) * 100
            out["spread_bps"] = stated + out["pik_bps"]
        elif inc:    # the stated spread already includes the PIK part
            out["pik_kind"], out["pik_bps"] = "included", Decimal(inc.group(1)) * 100
            out["spread_bps"] = stated
        elif plain:  # "SF + 7.75% PIK": the whole stated spread is paid in kind
            out["pik_kind"], out["pik_bps"] = "all_pik", stated
            out["spread_bps"] = stated
        else:
            out["spread_bps"] = stated
        return out
    eq = _EQUITY_PLUS.match(raw)
    if eq:           # "Equity plus 12.50% PIK": a preferred equity coupon, no spread
        out["ref_code"], out["reference_rate"] = eq.group(1).upper(), eq.group(1).upper()
        out["pik_kind"], out["pik_bps"] = "cash_plus", Decimal(eq.group(2)) * 100
        return out
    fx = _FIXED_ANY.match(raw)
    if fx and re.match(rf"^\s*(?:N/A\s+)?{_NUM}\s*%\s*Floor", raw, re.I):
        return out   # "7.00% Floor": only a floor is printed, no rate and no reference code
    if fx:           # fixed rate: no spread
        out["reference_rate"], out["ref_code"] = "FIXED", "FIXED"
        cp, inc, plain = _CASH_PLUS_PIK.search(raw), _INCL_PIK.search(raw), _PLAIN_PIK.search(raw)
        if cp:
            out["pik_kind"], out["pik_bps"] = "cash_plus", Decimal(cp.group(1)) * 100
        elif inc:
            out["pik_kind"], out["pik_bps"] = "included", Decimal(inc.group(1)) * 100
        elif plain:
            out["pik_kind"], out["pik_bps"] = "all_pik", Decimal(plain.group(1)) * 100
    return out


_HPS_FLOOR = re.compile(rf"interest rate floor on these investments as of [^.]*? was {_NUM}\s*%", re.I)
_HPS_NO_FLOOR = re.compile(r"There are no interest rate floors", re.I)


def hps_floor_bps(footnotes: str | None) -> tuple[Decimal | None, bool]:
    """Floor from the HPS footnote text. Returns (floor_bps, conflict). 'No interest rate floors' is 0,
    silence is None."""
    if not footnotes:
        return None, False
    vals = {Decimal(v) * 100 for v in _HPS_FLOOR.findall(footnotes)}
    none = bool(_HPS_NO_FLOOR.search(footnotes))
    if vals:
        return (min(vals) if len(vals) == 1 else sorted(vals)[0]), (len(vals) > 1 or none)
    return (Decimal(0) if none else None), False


# --------------------------------------------------------------------------- dates, money, currency
_DATE_MDY = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
_DATE_MY = re.compile(r"\b(\d{1,2})/(\d{4})\b")
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


def month_end(year: int, month: int) -> date:
    import calendar
    return date(year, month, calendar.monthrange(year, month)[1])


def parse_maturity(raw: str | None) -> date | None:
    """m/d/yyyy, ISO, or M/YYYY (the month end). Text after the date is ignored."""
    if not raw:
        return None
    m = _DATE_ISO.search(raw)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _DATE_MDY.search(raw)
    if m:
        return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    m = _DATE_MY.search(raw)
    if m:
        return month_end(int(m.group(2)), int(m.group(1)))
    return None


def currency(unit: str | None) -> str | None:
    if not unit:
        return None
    u = unit.strip().upper()
    return u[2:] if u.startswith("U_") else u


def dec(text: str | None) -> Decimal | None:
    if text is None or text == "":
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def pct_par(fair_value: Decimal | None, principal: Decimal | None) -> Decimal | None:
    """100 * fair value / principal. NULL when either is missing or the principal is zero: never divides by zero."""
    if fair_value is None or principal is None or principal == 0:
        return None
    try:
        return Decimal(100) * fair_value / principal
    except DivisionByZero:
        return None


def excluded_reason(*, type_norm: str, principal: Decimal | None, unfunded: bool, ccy: str | None,
                    fair_value: Decimal | None, cfg: dict) -> str | None:
    """One reason per row, first match in the configured order."""
    checks = {
        "EQUITY_POSITION": type_norm == "EQUITY",
        "ZERO_OR_NULL_PRINCIPAL": principal is None or principal == 0,
        "UNFUNDED_COMMITMENT": unfunded,
        "NON_USD_PRINCIPAL": ccy != "USD",
        "NULL_FAIR_VALUE": fair_value is None,
    }
    for reason in cfg["normalization"]["excluded_reason_order"]:
        if checks[reason]:
            return reason
    return None


def matches(pattern: str | None, text: str | None) -> bool:
    return bool(pattern) and pattern.lower() in (text or "").lower()


# --------------------------------------------------------------------------- one row
def normalize_row(raw: dict, filer_key: str, filer_cfg: dict, cfg: dict) -> dict:
    n = cfg["normalization"]
    name = raw["portfolio_company_raw"] or ""
    if filer_key in n["strip_industry_prefix_filers"]:
        name = strip_industry_prefix(name, raw["industry_raw"])
    if filer_key in n["collapse_repeated_prefix_filers"]:
        name = collapse_repeated_prefix(name)
    borrower, fallback = normalize_name(name, cfg)
    type_norm = normalize_instrument(raw["instrument_type_raw"], cfg)
    rate = parse_rate(raw["interest_rate_raw"], cfg)
    floor, floor_conflict = rate["floor_bps"], False
    if filer_key == "hps":
        floor, floor_conflict = hps_floor_bps(raw["footnotes_raw"])
    elif filer_key == "orcic":
        floor = None
    principal, fv = dec(raw["principal_raw"]), dec(raw["fair_value_raw"])
    ccy = currency(raw["principal_unit_raw"])
    unfunded = matches(filer_cfg.get("unfunded_pattern"), raw["footnotes_raw"])
    reason = excluded_reason(type_norm=type_norm, principal=principal, unfunded=unfunded, ccy=ccy,
                             fair_value=fv, cfg=cfg)
    return {
        "holding_id": raw["holding_id"], "bdc_cik": raw["cik"], "period_end_date": raw["period_end_date"],
        "borrower_normalized": borrower, "industry": raw["industry_raw"], "instrument_type_norm": type_norm,
        "reference_rate": rate["reference_rate"], "spread_bps": rate["spread_bps"], "floor_bps": floor,
        "pik_bps": rate["pik_bps"], "maturity_date": parse_maturity(raw["maturity_date_raw"]),
        "principal": principal, "principal_currency": ccy, "cost": dec(raw["cost_raw"]), "fair_value": fv,
        "fair_value_pct_par": None if reason else pct_par(fv, principal),
        "footnotes": raw["footnotes_raw"], "source_url": raw["source_url"],
        "non_accrual": matches(filer_cfg.get("non_accrual_pattern"), raw["footnotes_raw"]),
        "excluded_reason": reason,
        "_name_fallback": fallback, "_floor_conflict": floor_conflict, "_rate": rate,
        "_raw_type": raw["instrument_type_raw"], "_raw_rate": raw["interest_rate_raw"],
    }


COLUMNS = ["holding_id", "bdc_cik", "period_end_date", "borrower_normalized", "industry", "instrument_type_norm",
           "reference_rate", "spread_bps", "floor_bps", "pik_bps", "maturity_date", "principal",
           "principal_currency", "cost", "fair_value", "fair_value_pct_par", "footnotes", "source_url",
           "non_accrual", "excluded_reason"]

UPSERT = (
    f"INSERT INTO normalized_holdings ({', '.join(COLUMNS)}) VALUES ({', '.join(['%s'] * len(COLUMNS))}) "
    "ON CONFLICT (holding_id) DO UPDATE SET " + ", ".join(f"{c} = EXCLUDED.{c}" for c in COLUMNS[1:])
)


def refuse_if_frozen(conn, module: str) -> None:
    if conn.execute("SELECT 1 FROM matcher_freeze").fetchone():
        raise SystemExit(f"{module} refuses to run: the matcher is frozen (matcher_freeze has a row).")


def load_raw(conn, period: date) -> list[dict]:
    cur = conn.execute(
        "SELECT h.holding_id, f.cik, f.period_end_date, h.portfolio_company_raw, h.industry_raw, "
        "h.instrument_type_raw, h.interest_rate_raw, h.maturity_date_raw, h.principal_raw, h.principal_unit_raw, "
        "h.cost_raw, h.fair_value_raw, h.footnotes_raw, h.source_url "
        "FROM raw_holdings h JOIN raw_filings f USING (filing_id) WHERE f.period_end_date = %s "
        "ORDER BY h.holding_id", (period,))
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def run(conn, period: date, cfg: dict | None = None, verbose: bool = True) -> list[dict]:
    cfg = cfg or load_config()
    refuse_if_frozen(conn, "normalize")
    by_cik = {f["cik"]: (key, f) for key, f in cfg["filers"].items()}
    raws = load_raw(conn, period)
    out = []
    for raw in raws:
        key, fcfg = by_cik[raw["cik"]]
        row = normalize_row(raw, key, fcfg, cfg)
        row["_filer"] = key
        out.append(row)
    with conn.transaction():
        with conn.cursor() as cur:
            cur.executemany(UPSERT, [tuple(r[c] for c in COLUMNS) for r in out])
    if verbose:
        report(out)
    return out


# --------------------------------------------------------------------------- printed report
def report(rows: list[dict]) -> None:
    filers = sorted({r["_filer"] for r in rows})
    print(f"normalized {len(rows)} rows")
    print("\n== distinct raw instrument types -> normalized type, per filer (rows)")
    for f in filers:
        c = Counter((r["_raw_type"], r["instrument_type_norm"]) for r in rows if r["_filer"] == f)
        print(f"-- {f}")
        for (raw, norm), n in sorted(c.items(), key=lambda x: (-x[1], str(x[0][0]))):
            print(f"   {n:>4}  {str(raw)[:62]:<62} -> {norm}")
    print("\n== reference rate codes seen, per filer (rows) and their stored value")
    for f in filers:
        c = Counter((r["_rate"]["ref_code"], r["_rate"]["reference_rate"]) for r in rows if r["_filer"] == f and r["_rate"]["ref_code"])
        print(f"-- {f}: " + ", ".join(f"{code}->{ref} {n}" for (code, ref), n in sorted(c.items(), key=lambda x: -x[1])))
    print("\n== PIK phrasings per filer (digits shown as #), kind, example, parsed (spread_bps total, pik_bps)")
    for f in filers:
        c: dict = defaultdict(lambda: [0, None])
        for r in rows:
            if r["_filer"] == f and r["_rate"]["pik_kind"] != "none":
                pat = re.sub(r"\d+(?:\.\d+)?", "#", r["_raw_rate"])
                c[(pat, r["_rate"]["pik_kind"])][0] += 1
                c[(pat, r["_rate"]["pik_kind"])][1] = (r["_raw_rate"], r["spread_bps"], r["pik_bps"])
        print(f"-- {f}")
        for (pat, kind), (n, ex) in sorted(c.items(), key=lambda x: -x[1][0]):
            print(f"   {n:>3}  [{kind}] {pat:<44} e.g. {ex[0]!r} -> spread_bps {ex[1]}, pik_bps {ex[2]}")
    print("\n== floors")
    for f in filers:
        fr = [r for r in rows if r["_filer"] == f]
        print(f"-- {f}: floor_bps set {sum(1 for r in fr if r['floor_bps'] is not None and r['floor_bps'] > 0)}, "
              f"zero (no floor) {sum(1 for r in fr if r['floor_bps'] == 0)}, NULL {sum(1 for r in fr if r['floor_bps'] is None)}, "
              f"conflicting footnotes {sum(1 for r in fr if r['_floor_conflict'])}")
    print("\n== non_accrual and excluded_reason per filer")
    for f in filers:
        fr = [r for r in rows if r["_filer"] == f]
        c = Counter(r["excluded_reason"] for r in fr)
        print(f"-- {f}: rows {len(fr)}, non_accrual {sum(1 for r in fr if r['non_accrual'])}, "
              f"with a % of par {sum(1 for r in fr if r['fair_value_pct_par'] is not None)}; "
              + ", ".join(f"{k or 'NONE'} {v}" for k, v in sorted(c.items(), key=lambda x: (x[0] is None, str(x[0])))))
    out_of_range = [r for r in rows if r["fair_value_pct_par"] is not None and not (0 <= r["fair_value_pct_par"] <= 150)]
    print(f"\nfair_value_pct_par outside 0 to 150: {len(out_of_range)} rows")
    for r in out_of_range:
        print(f"   {r['_filer']} holding {r['holding_id']} {r['borrower_normalized'][:40]!r}: principal {r['principal']} "
              f"{r['principal_currency']} fair value {r['fair_value']} -> {r['fair_value_pct_par']:.2f}")
    print(f"names that fell back to the cleaned name (empty after dropping tokens): {sum(1 for r in rows if r['_name_fallback'])}")


def main() -> int:
    import os
    load_env_file()
    period = measured_period_end()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        cfg = load_config()
        run(conn, period, cfg, verbose=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
