"""Day 1 read-only: parse the Schedule of Investments HTML tables for HPS and ORCIC
and compare them with the XBRL rows. No database, no network.

Run: python -m pipeline.scout_html
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from lxml import etree

RAW = Path(__file__).resolve().parent.parent / "fixtures" / "raw"
PE = "2026-06-30"
FILERS = ("hps_corporate_lending", "blue_owl_credit_income")
AMOUNT_SCALE = 1000  # both tables are printed in thousands (checked by the join rate)

CURRENCY_CELLS = {"$", "€", "£", "C$", "A$", "NZ$", "S$", "kr", "¥", "₩", "CHF", "DKK", "NOK", "SEK"}
AMOUNT_RE = re.compile(r"^\(?\d{1,3}(,\d{3})*\)?$|^\(?\d+\)?$")
DATE_RE = re.compile(r"^(\d{1,2}/\d{1,2}/\d{4}|\d{1,2}/\d{4})$")
RATE_REF_RE = re.compile(r"^[A-Z]{1,4}\s*\+$|^N/A$|^Fixed$|^[A-Z]{1,6}$")
DASHES = {"—", "–", "-"}
TYPE_WORDS = ("lien", "loan", "stock", "interest", "equity", "facility", "notes", "shares",
              "warrant", "units", "preferred", "debt", "revolver", "term")


def _ln(e) -> str:
    return e.tag.split("}")[-1].lower() if isinstance(e.tag, str) else ""


def _row_cells(tr) -> list[str]:
    return [" ".join("".join(td.itertext()).split()) for td in tr if _ln(td) in ("td", "th")]


def _num(tok: str) -> Decimal | None:
    t = tok.strip()
    if t in DASHES or not AMOUNT_RE.match(t):
        return None
    neg = t.startswith("(")
    v = Decimal(t.strip("()").replace(",", ""))
    return -v if neg else v


def _tables(root) -> list:
    return [e for e in root.iter() if _ln(e) == "table"]


def _first_cell(table) -> str:
    for tr in table.iter():
        if _ln(tr) == "tr":
            cells = [c for c in _row_cells(tr) if c]
            if cells:
                return cells[0]
    return ""


def _table_text(table) -> str:
    return " ".join("".join(table.itertext()).split())


def soi_and_unfunded_tables(root) -> tuple[list, list]:
    """First contiguous run of 'Company...' tables is the June schedule. The run of
    tables mentioning 'Commitment' right after it holds the unfunded commitments."""
    tabs = _tables(root)
    soi, unf = [], []
    i = 0
    while i < len(tabs) and not _first_cell(tabs[i]).startswith("Company"):
        i += 1
    while i < len(tabs) and _first_cell(tabs[i]).startswith("Company"):
        soi.append(tabs[i])
        i += 1
    # skip non-schedule tables (swaps) until the unfunded run
    while i < len(tabs) and "Commitment" not in _table_text(tabs[i])[:200]:
        i += 1
    while i < len(tabs) and "Commitment" in _table_text(tabs[i])[:200]:
        unf.append(tabs[i])
        i += 1
    return soi, unf


def load_root(label: str):
    return etree.parse(str(RAW / f"{label}_10q_{PE}.htm"),
                       etree.XMLParser(huge_tree=True, recover=True)).getroot()


def parse_schedule(label: str) -> dict:
    """Returns {'rows': [...], 'headers': Counter, 'totals': [...], 'unfunded': [...]}."""
    soi, unf = soi_and_unfunded_tables(load_root(label))
    out = parse_tables(label, soi)
    out["unfunded"] = parse_unfunded(unf)
    out["soi_tables"] = len(soi)
    out["unfunded_tables"] = len(unf)
    return out


def parse_tables(label: str, soi: list) -> dict:
    rows, totals, headers = [], [], Counter()
    ctx = {"affil": None, "section": None, "industry": None}
    for t in soi:
        for tr in t.iter():
            if _ln(tr) != "tr":
                continue
            raw = _row_cells(tr)
            cur = next((c for c in raw if c in CURRENCY_CELLS), None)
            toks = [c for c in raw if c and c not in CURRENCY_CELLS and c != "%"]
            if not toks:
                continue
            first = toks[0]
            if first.startswith(("Company(", "Ref. Rate")):
                continue
            if first.lower().startswith("total"):
                totals.append({"name": first, "amounts": [_num(x) for x in toks[1:] if _num(x) is not None],
                               "raw": toks})
                continue
            if len(toks) == 1:
                headers[first] += 1
                low = first.lower()
                if "controlled" in low or "affiliated" in low:
                    ctx["affil"] = first
                elif re.search(r"(debt|equity|joint venture|investments)", low) and len(first) < 50:
                    ctx["section"] = first
                else:
                    ctx["industry"] = first
                continue
            if _num(first) is not None and all(_num(x) is not None or x in DASHES or "." in x for x in toks):
                continue  # unlabelled industry subtotal (ORCIC)
            mat_i = next((i for i, x in enumerate(toks) if i > 0 and DATE_RE.match(x)), None)
            tail = toks[(mat_i + 1 if mat_i is not None else 1):]
            if mat_i is None:
                # equity row: skip rate tokens, keep amounts and dashes (N/A is a maturity placeholder)
                tail = [x for x in tail if x not in ("N/A",)]
            amts = [(_num(x) if x not in DASHES else None) for x in tail
                    if _num(x) is not None or x in DASHES]
            inst = next((x for x in toks[1:] if not DATE_RE.match(x) and not RATE_REF_RE.match(x)
                         and not _num(x) and any(w in x.lower() for w in TYPE_WORDS)
                         and "%" not in x), None)
            n = len(amts)
            need = 4 if label == "blue_owl_credit_income" else 3
            # HPS equity rows print units, not par. ORCIC prints par for every row.
            has_par = mat_i is not None or label == "blue_owl_credit_income"
            principal = amts[-need] if (n >= need and has_par) else None
            # a printed dash in the cost or fair value column means zero
            cost = (amts[-2] if amts[-2] is not None else Decimal(0)) if n >= 2 else None
            fv = (amts[-1] if amts[-1] is not None else Decimal(0)) if n >= 1 else None
            rows.append({
                "name": first, "instrument_type_row": inst, "section": ctx["section"],
                "affil": ctx["affil"], "industry": ctx["industry"],
                "maturity": toks[mat_i] if mat_i is not None else None,
                "principal": principal, "cost": cost, "fair_value": fv,
                "currency_cell": cur, "raw": toks,
            })
    return {"rows": rows, "headers": headers, "totals": totals}


def parse_unfunded(unf: list) -> list[dict]:
    unfunded = []
    for t in unf:
        for tr in t.iter():
            if _ln(tr) != "tr":
                continue
            toks = [c for c in _row_cells(tr) if c and c not in CURRENCY_CELLS and c != "%"]
            if len(toks) >= 3 and _num(toks[-1]) is not None or (toks and toks[-1] in DASHES and len(toks) >= 3):
                unfunded.append({"name": toks[0], "raw": toks, "fair_value": _num(toks[-1])})
    return unfunded


def xbrl_rows(label: str):
    from pipeline.ixbrl import parse_ixbrl, assemble_investments, split_pipe_identifier
    ctxs, facts, texts = parse_ixbrl(RAW / f"{label}_10q_{PE}.htm")
    rows = assemble_investments(ctxs, facts, texts, PE, identifier_parser=split_pipe_identifier)
    return ctxs, facts, rows


def _key(p, c, f, scale=1):
    def r(v):
        return None if v is None else int(Decimal(v) * scale)
    return (r(p), r(c), r(f))


def join(html_rows: list[dict], xrows: list[dict]) -> dict:
    sched = [r for r in xrows if r["fair_value"] is not None or r["cost"] is not None]
    idx = defaultdict(list)
    for i, r in enumerate(sched):
        idx[_key(r["principal"], r["cost"], r["fair_value"])].append(i)
    html_data = [r for r in html_rows if r["cost"] is not None or r["fair_value"] is not None]
    matched = multi = 0
    used = set()
    unmatched_html = []
    for h in html_data:
        hits = idx.get(_key(h["principal"], h["cost"], h["fair_value"], AMOUNT_SCALE), [])
        if hits:
            matched += 1
            multi += len(hits) > 1
            used.update(hits)
        else:
            unmatched_html.append(h)
    funded = [i for i, r in enumerate(sched) if r["principal"] not in (None, 0)]
    return {"html_data": len(html_data), "matched": matched, "multi": multi,
            "xbrl_schedule": len(sched), "xbrl_funded": len(funded),
            "xbrl_funded_unmatched": [i for i in funded if i not in used],
            "xbrl_unmatched_all": [i for i in range(len(sched)) if i not in used],
            "unmatched_html": unmatched_html, "sched": sched, "idx": idx}


def main() -> None:
    which = sys.argv[1:] or list(FILERS)
    for label in which:
        print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")
        s = parse_schedule(label)
        rows = s["rows"]
        print(f"schedule tables {s['soi_tables']}, unfunded tables {s['unfunded_tables']}, "
              f"data rows {len(rows)}, total rows {len(s['totals'])}, unfunded rows {len(s['unfunded'])}")
        print("header rows (count):", dict(s["headers"].most_common(14)))
        for r in rows[:5]:
            print("  SAMPLE", {k: r[k] for k in ("name", "instrument_type_row", "section", "maturity",
                                                  "principal", "cost", "fair_value", "currency_cell")})
        ctxs, facts, xr = xbrl_rows(label)
        j = join(rows, xr)
        print(f"JOIN html_data={j['html_data']} matched={j['matched']} multi={j['multi']} "
              f"unmatched_html={len(j['unmatched_html'])} xbrl_schedule={j['xbrl_schedule']} "
              f"xbrl_funded={j['xbrl_funded']} funded_unmatched={len(j['xbrl_funded_unmatched'])} "
              f"xbrl_unmatched_all={len(j['xbrl_unmatched_all'])}")


if __name__ == "__main__":
    main()
