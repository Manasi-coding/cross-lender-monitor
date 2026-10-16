"""Read-only data report: python -m pipeline.report writes docs/data_report.md.

Only SELECT statements run, inside a read-only transaction. Every number comes from the database or
from config.yaml. Blocking efficiency and run times are added after the matcher exists (Phase 4).
The overlap section uses a crude name normalization for counting only. It is not the matcher.
"""
from __future__ import annotations

import os
import re
import sys
from collections import defaultdict
from pathlib import Path

import psycopg

from pipeline.config import load_config, load_env_file, measured_period_end

REPORT_PATH = Path(__file__).resolve().parent.parent / "docs" / "data_report.md"

# crude, report-only tokens dropped before comparing names for the overlap counts
LEGAL = {"inc", "llc", "lp", "ltd", "limited", "corp", "corporation", "co", "company", "holdings",
         "holding", "gmbh", "sarl", "sa", "bv", "plc", "ag", "llp", "l", "p", "pty", "ulc", "the",
         "fka", "dba", "aka"}
SPREAD_TOKEN = re.compile(r"[A-Za-z]{1,6}\s*\+\s*\d|\bSOFR\b|\bSONIA\b|\bEURIBOR\b", re.I)
FLOOR_TOKEN = re.compile(r"floor", re.I)
PIK_TOKEN = re.compile(r"\bPIK\b", re.I)


def unit_code(unit: str | None) -> str | None:
    if unit is None:
        return None
    u = unit.lower()
    return (u[2:] if u.startswith("u_") else u).upper()


def name_tokens(name: str) -> tuple[str, ...]:
    s = re.sub(r"\(.*?\)", " ", name.lower())
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return tuple(t for t in s.split() if t not in LEGAL)


def md_table(header: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def pct(n: int, d: int) -> str:
    return f"{100 * n / d:.1f}%" if d else "not measurable (0 rows)"


def load_rows(conn) -> dict[str, dict]:
    """filer key -> {'filing': row, 'rows': [dict]} for the measured period, in config order."""
    cfg = load_config()["filers"]
    period = measured_period_end()
    out: dict[str, dict] = {}
    for key, f in cfg.items():
        filing = conn.execute(
            "SELECT filing_id, bdc_name, cik, accession_number, period_end_date, filing_date, form_type, source_url "
            "FROM raw_filings WHERE cik = %s AND period_end_date = %s", (f["cik"], period)).fetchone()
        if filing is None:
            out[key] = {"filing": None, "rows": []}
            continue
        cur = conn.execute(
            "SELECT holding_id, portfolio_company_raw, industry_raw, instrument_type_raw, interest_rate_raw, "
            "maturity_date_raw, principal_raw, principal_unit_raw, cost_raw, fair_value_raw, footnotes_raw "
            "FROM raw_holdings WHERE filing_id = %s ORDER BY row_order", (filing[0],))
        cols = [d.name for d in cur.description]
        out[key] = {"filing": filing, "rows": [dict(zip(cols, r)) for r in cur.fetchall()]}
    return out


def is_funded(r: dict) -> bool:
    return r["principal_raw"] not in (None, "") and float(r["principal_raw"]) != 0 and r["fair_value_raw"] is not None


def section_parse(data: dict, cfg: dict) -> str:
    rows_out, cur_out = [], []
    for key, d in data.items():
        f, rows = d["filing"], d["rows"]
        if f is None:
            rows_out.append([key, "not loaded"] + [""] * 11)
            continue
        with_principal = [r for r in rows if r["principal_raw"] is not None]
        funded_rows = [r for r in rows if r["principal_raw"] not in (None, "") and float(r["principal_raw"]) != 0]
        parsed = [r for r in funded_rows if r["fair_value_raw"] is not None]
        with_fv = [r for r in rows if r["fair_value_raw"] is not None]
        with_fn = [r for r in rows if r["footnotes_raw"]]
        by_cur: dict[str, int] = defaultdict(int)
        for r in funded_rows:
            c = unit_code(r["principal_unit_raw"]) or "UNKNOWN"
            if c != "USD":
                by_cur[c] += 1
        non_usd = sum(by_cur.values())
        rows_out.append([f"{f[1]} ({key})", f[3], len(rows), len(with_principal), len(funded_rows), len(with_fv),
                         len(parsed), pct(len(parsed), len(funded_rows)), pct(len(parsed), len(rows)),
                         len(with_fn), non_usd])
        cur_out.append([key, non_usd] + [f"{c} {n}" for c, n in sorted(by_cur.items(), key=lambda x: (-x[1], x[0]))])
    t1 = md_table(["Filing", "Accession", "Rows total", "Rows with principal", "Funded rows (nonzero principal)",
                   "Rows with fair value", "Funded rows with fair value (parsed)", "Funded-row parse rate",
                   "All-rows parse rate", "Rows with footnotes", "Funded rows, non-USD principal"], rows_out)
    lines = [t1, "",
             "Rows total is the schedule rows loaded into raw_holdings. A funded row has a nonzero principal. "
             "The funded-row rate is funded rows with a fair value over funded rows. The all-rows rate is the same "
             "numerator over rows total, so it is lower wherever unfunded commitments and equity are in the schedule. "
             "The two rates are reported separately on purpose.", "",
             "Non-USD principal on funded rows, by currency:", ""]
    for r in cur_out:
        lines.append(f"- {r[0]}: {r[1]} rows" + (" (" + ", ".join(r[2:]) + ")" if len(r) > 2 else ""))
    return "\n".join(lines)


def section_equity(data: dict, cfg: dict) -> str:
    kws = [k.lower() for k in cfg["normalization"]["equity_keywords"]]
    rows_out = []
    for key, d in data.items():
        rows = d["rows"]
        eq = [r for r in rows if any(k in (r["instrument_type_raw"] or "").lower() for k in kws)]
        nz = [r for r in eq if r["principal_raw"] not in (None, "") and float(r["principal_raw"]) != 0]
        rows_out.append([key, len(eq), len(nz)])
    return (md_table(["Filer", "Equity-like rows", "of which nonzero principal"], rows_out) +
            "\n\nEquity-like means instrument_type_raw contains one of the normalization.equity_keywords in config.yaml "
            f"({', '.join(kws)}). The keyword list is matched against the type text only. Rows whose type text is an "
            "interest or fund label that is not in the list (for example 'LP Interest') are not counted: unexplained "
            "until normalize defines the rule. Equity rows can carry a share count in the principal field.")


def section_footnotes(data: dict, cfg: dict) -> str:
    rows_out = []
    for key, d in data.items():
        rows = d["rows"]
        f = cfg["filers"][key]

        def count(pattern):
            if not pattern:
                return ("no pattern", "no pattern")
            hit = [r for r in rows if pattern.lower() in (r["footnotes_raw"] or "").lower()]
            return (len(hit), sum(1 for r in hit if is_funded(r)))

        unf, unf_f = count(f["unfunded_pattern"])
        na, na_f = count(f["non_accrual_pattern"])
        generic = [r for r in rows if "unfunded" in (r["footnotes_raw"] or "").lower()]
        rows_out.append([key, repr(f["unfunded_pattern"]), unf, unf_f, repr(f["non_accrual_pattern"]), na, na_f,
                         len(generic), sum(1 for r in generic if is_funded(r))])
    return (md_table(["Filer", "Unfunded pattern", "Unfunded rows", "of which funded", "Non-accrual pattern",
                      "Non-accrual rows", "of which funded", "Rows with a generic 'unfunded' footnote",
                      "of which funded"], rows_out) +
            "\n\nPatterns are the case-insensitive substrings configured per filer, matched against the footnote text "
            "linked to each row. 'Funded' means nonzero principal and a fair value. The generic column shows what a "
            "plain 'unfunded' match would flag: it is not a rule, it is the reason the pattern is per filer.")


def section_rates(data: dict) -> str:
    rows_out = []
    for key, d in data.items():
        strings = [r["interest_rate_raw"] for r in d["rows"] if r["interest_rate_raw"]]
        rows_out.append([key, len(d["rows"]), len(strings),
                         sum(1 for s in strings if SPREAD_TOKEN.search(s)),
                         sum(1 for s in strings if FLOOR_TOKEN.search(s)),
                         sum(1 for s in strings if PIK_TOKEN.search(s))])
    return (md_table(["Filer", "Rows", "interest_rate_raw present", "with a spread token", "with a floor token",
                      "with a PIK token"], rows_out) +
            "\n\nCounts only: a spread token is a reference rate followed by a plus and a number (S+425, SF + 5.00%), "
            "a floor token is the word Floor, a PIK token is the word PIK. No parsing and no new columns. "
            "Rows without a rate string are mostly unfunded commitments and equity.")


def tokens_by_filer(data: dict) -> dict[str, dict[tuple, bool]]:
    """name tokens -> True when at least one funded row of that name has USD principal."""
    out: dict[str, dict[tuple, bool]] = {}
    for key, d in data.items():
        names: dict[tuple, bool] = {}
        for r in d["rows"]:
            if not is_funded(r):
                continue
            t = name_tokens(r["portfolio_company_raw"] or "")
            if len("".join(t)) < 6:
                continue
            names[t] = names.get(t, False) or unit_code(r["principal_unit_raw"]) == "USD"
        out[key] = names
    return out


def section_overlap(data: dict) -> str:
    T = tokens_by_filer(data)
    ads, hps, orcic = T["ads"], T["hps"], T["orcic"]

    def amatch(t):  # ADS names carry an industry prefix, so the other filer's name is a tail of the ADS name
        for a in ads:
            if len(a) >= len(t) and a[len(a) - len(t):] == t:
                return a
        return None

    m_h = {t for t in hps if amatch(t)}
    m_o = {t for t in orcic if amatch(t)}
    common = {t for t in hps if t in orcic}

    def usd(S):
        return {t for t in S if hps.get(t, True) and orcic.get(t, True) and (not amatch(t) or ads[amatch(t)])}

    union, three = m_h | m_o | common, m_h & m_o & common
    three_usd = {t for t in three if hps[t] and orcic[t] and ads[amatch(t)]}
    pair_usd = lambda S, X: {t for t in S if X[t] and (not amatch(t) or ads[amatch(t)])}
    rows = [
        ["ADS and HPS", len(m_h), len(pair_usd(m_h, hps))],
        ["ADS and ORCIC", len(m_o), len(pair_usd(m_o, orcic))],
        ["HPS and ORCIC", len(common), len({t for t in common if hps[t] and orcic[t]})],
        ["In 2 or more of the 3 BDCs", len(union), len(usd(union))],
        ["In all 3", len(three), len(three_usd)],
    ]
    return (md_table(["Distinct borrower names", "With non-USD rows (all)", "Without non-USD rows (USD only)"], rows) +
            "\n\nRe-run on the ingested raw_holdings (funded rows only). Name match: lowercase, parentheticals and "
            "punctuation removed, legal-form tokens dropped; for ADS the other filer's name must equal the tail of "
            "the ADS name, which carries an industry prefix. 'USD only' keeps a name only when every compared filer "
            "has a USD-principal row for it. This is a crude count for the 30-name gate, not the matcher.")


def build(conn) -> str:
    cfg = load_config()
    period = measured_period_end()
    data = load_rows(conn)
    parts = [
        "# Data report",
        f"Measured quarter {period}. Generated by `python -m pipeline.report` (read only). Every number comes "
        "from the database or config.yaml. Blocking efficiency and run times are added after the matcher is built.",
        "",
        "## 1. Ingest and parse rates per filing", section_parse(data, cfg), "",
        "## 2. Equity-like rows with nonzero principal", section_equity(data, cfg), "",
        "## 3. Unfunded-commitment and non-accrual footnotes", section_footnotes(data, cfg), "",
        "## 4. Rate strings: spread, floor and PIK tokens", section_rates(data), "",
        "## 5. Cross-BDC borrower overlap on the ingested data", section_overlap(data), "",
    ]
    return "\n".join(parts)


def main() -> int:
    load_env_file()
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not set.")
    with psycopg.connect(url) as conn:
        conn.read_only = True
        text = build(conn)
    REPORT_PATH.write_text(text, encoding="utf-8")
    print(f"wrote {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
