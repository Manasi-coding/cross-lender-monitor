"""Builds the trimmed real excerpts used by the schema drift tests (SPEC test 7 and test 26).

Run once, locally, with the full filings in fixtures/raw/ (gitignored):
    python fixtures/make_excerpts.py
The excerpts (fixtures/*_excerpt.htm) are committed so CI needs no SEC access. Each one keeps the
real XBRL contexts, units, facts and footnotes of at most 30 rows, plus the real table rows for the
HTML-assisted filers. Nothing is typed in by hand or altered.
"""
from __future__ import annotations

import copy
import sys
from datetime import date
from pathlib import Path

from lxml import etree

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.adapters import Filing, ads_industry_names, make_adapter  # noqa: E402
from pipeline.config import load_config  # noqa: E402
from pipeline.html_schedule import main_schedule_tables, parse_main_schedule  # noqa: E402
from pipeline.ixbrl import IDENTIFIER_AXIS, NS_IX, NS_XBRLDI, NS_XBRLI, parse_ixbrl  # noqa: E402

XHTML = "http://www.w3.org/1999/xhtml"
RAW = ROOT / "fixtures" / "raw"
OUT = ROOT / "fixtures"
MAX_ROWS = 30


def q(ns: str, name: str) -> str:
    return f"{{{ns}}}{name}"


def ln(e) -> str:
    return e.tag.split("}")[-1].lower() if isinstance(e.tag, str) else ""


def build(src: Path, root, out: Path, pe: str, identifiers: set[str], trs: list, header_tr, note: str) -> None:
    contexts, _facts, _text = parse_ixbrl(src)
    keep_ctx = {cid for cid, c in contexts.items()
                if c.instant == pe and len(c.dims) == 1 and c.typed.get(IDENTIFIER_AXIS) in identifiers}
    ctx_el = {e.get("id"): e for e in root.iter(q(NS_XBRLI, "context"))}
    unit_el = {e.get("id"): e for e in root.iter(q(NS_XBRLI, "unit"))}

    fact_tags = (q(NS_IX, "nonFraction"), q(NS_IX, "nonNumeric"))
    # facts that travel inside a copied table row. The list keeps the lxml proxies alive, so identity is stable.
    nested_list = [f for tr in trs for f in tr.iter(*fact_tags)]
    nested = set(nested_list)
    standalone = [f for f in root.iter(*fact_tags) if f.get("contextRef") in keep_ctx and f not in nested]
    all_kept = [f for f in root.iter(*fact_tags) if f.get("contextRef") in keep_ctx or f in nested]
    kept_ids = {f.get("id") for f in all_kept if f.get("id")}

    nsmap = {None: XHTML, "ix": NS_IX, "xbrli": NS_XBRLI, "xbrldi": NS_XBRLDI}
    html = etree.Element(q(XHTML, "html"), nsmap=nsmap)
    html.append(etree.Comment(f" {note} "))
    body = etree.SubElement(html, q(XHTML, "body"))
    hidden = etree.SubElement(body, q(XHTML, "div"), style="display:none")
    header = etree.SubElement(hidden, q(NS_IX, "header"))
    resources = etree.SubElement(header, q(NS_IX, "resources"))

    used_units = {f.get("unitRef") for f in all_kept if f.get("unitRef")}
    for cid in sorted(keep_ctx):
        resources.append(copy.deepcopy(ctx_el[cid]))
    for uid in sorted(used_units):
        if uid in unit_el:
            resources.append(copy.deepcopy(unit_el[uid]))

    footnote_ids: list[str] = []
    for rel in root.iter(q(NS_IX, "relationship")):
        frm = [r for r in (rel.get("fromRefs") or "").split() if r in kept_ids]
        if not frm:
            continue
        new = copy.deepcopy(rel)
        new.set("fromRefs", " ".join(frm))
        resources.append(new)
        footnote_ids += [r for r in (rel.get("toRefs") or "").split() if r not in footnote_ids]
    notes = {e.get("id"): e for e in root.iter(q(NS_IX, "footnote"))}
    for fid in footnote_ids:
        if fid in notes:
            resources.append(copy.deepcopy(notes[fid]))

    if standalone:
        div = etree.SubElement(body, q(XHTML, "div"))
        for f in standalone:
            div.append(copy.deepcopy(f))
    if trs:
        table = etree.SubElement(body, q(XHTML, "table"))
        table.append(copy.deepcopy(header_tr))
        seen: set[int] = set()
        for tr in trs:
            for h in _HEADERS.get(id(tr), ()):
                if h is not None and id(h) not in seen:
                    seen.add(id(h))
                    table.append(copy.deepcopy(h))
            table.append(copy.deepcopy(tr))
    out.write_bytes(etree.tostring(html, encoding="utf-8", xml_declaration=True))
    n_tr = len(trs)
    print(f"{out.name}: {len(keep_ctx)} identifiers' contexts, {len(all_kept)} facts, {len(footnote_ids)} footnotes, "
          f"{n_tr} table rows, {out.stat().st_size:,} bytes")


_HEADERS: dict[int, tuple] = {}


def pick(rows, rules):
    """rules: list of (substring, how_many, optional predicate). Returns rows in order, no repeats."""
    chosen, seen = [], set()
    for sub, n, pred in rules:
        k = 0
        for r in rows:
            name = r[0]
            if sub.lower() in name.lower() and (pred is None or pred(r)) and id(r) not in seen:
                chosen.append(r)
                seen.add(id(r))
                k += 1
                if k >= n:
                    break
    return chosen


def make_ads(label: str, period: date, rules: list, out_name: str, note: str) -> None:
    cfg = load_config()["filers"]["ads"]
    src = RAW / f"{label}_10q_{period.isoformat()}.htm"
    filing = Filing(label, cfg["cik"], "x", period, src, "u", "a")
    adapter = make_adapter("ads", cfg)
    _c, _f, _t, schedule = adapter.load_xbrl(filing)
    chosen = pick([(r["identifier"], r) for r in schedule], rules)
    assert 0 < len(chosen) <= MAX_ROWS, len(chosen)
    root = etree.parse(str(src), etree.XMLParser(huge_tree=True, recover=True)).getroot()
    # the industry of each chosen row comes from the printed 'Total <industry>' rows, so keep those real rows too
    industries = ads_industry_names(src)
    aliases = cfg.get("industry_aliases") or {}
    prefixes = sorted(industries | set(aliases), key=len, reverse=True)
    wanted = set()
    for ident, _ in chosen:
        pre = next((p for p in prefixes if ident.startswith(p + " ")), None)
        if pre is not None:
            wanted.add("Total " + aliases.get(pre, pre))
    tables = [e for e in root.iter() if ln(e) == "table"]

    def cells(tr):
        return [c for c in (" ".join("".join(td.itertext()).split()) for td in tr if ln(td) in ("td", "th")) if c]

    totals, header_tr = [], None
    for tb in tables:
        trs_here = [tr for tr in tb.iter() if ln(tr) == "tr" and cells(tr)]
        if not trs_here or not cells(trs_here[0])[0].startswith("Industry/Company"):
            continue
        header_tr = header_tr if header_tr is not None else trs_here[0]
        totals += [tr for tr in trs_here if cells(tr)[0] in wanted and tr not in totals]
        if len(totals) >= len(wanted):
            break
    assert len(totals) == len(wanted), (len(totals), len(wanted))
    build(src, root, OUT / out_name, period.isoformat(), {r[0] for r in chosen}, totals, header_tr, note)


def make_html_assisted(key: str, rules: list, drop_rules: list, out_name: str, note: str) -> None:
    cfg = load_config()["filers"][key]
    period = date(2026, 6, 30)
    src = RAW / f"{cfg['fixture_label']}_10q_{period.isoformat()}.htm"
    filing = Filing(cfg["fixture_label"], cfg["cik"], "x", period, src, "u", "a")
    adapter = make_adapter(key, cfg)
    pairs, dropped, _notes = adapter.match(filing)
    chosen = pick([(hr.name, (hr, x)) for hr, x in pairs], rules)
    drops = pick([(x["raw_name"], x) for x in dropped], drop_rules)
    assert 0 < len(chosen) + len(drops) <= MAX_ROWS, len(chosen) + len(drops)
    idents = {r[1][1]["identifier"] for r in chosen} | {d[1]["identifier"] for d in drops}
    # the adapter parsed its own tree, so find the same table rows (same order) in a tree owned here
    root = etree.parse(str(src), etree.XMLParser(huge_tree=True, recover=True)).getroot()
    h = cfg["html"]
    mine = parse_main_schedule(src, h["amounts_after_maturity"], h["par_on_rows_without_maturity"], root=root)
    trs = []
    for r in chosen:
        row = mine[r[1][0].order]
        assert row.name == r[1][0].name
        trs.append(row.element)
        _HEADERS[id(row.element)] = row.header_elements
    def first_text(tr):
        return next((c for c in (" ".join("".join(td.itertext()).split()) for td in tr if ln(td) in ("td", "th")) if c), "")

    header_tr = next(tr for tr in main_schedule_tables(root)[0].iter() if ln(tr) == "tr" and first_text(tr).startswith("Company"))
    build(src, root, OUT / out_name, period.isoformat(), idents, trs, header_tr, note)


def main() -> None:
    make_ads("ads", date(2026, 6, 30), [
        ("Corpuls Heartbeat", 2, None), ("North American Rail Solutions", 6, None), ("IQN Holding", 2, None),
        ("SK Neptune Husky", 1, None), ("Virgin Media Secured", 1, None), ("ERC Topco", 2, None),
        ("DCA Investment Holding", 2, None), ("Hovnanian", 1, None), ("G2CI Evergreen", 2, None),
        ("Trading Technologies International", 1, None), ("Valor VCI Intermediate Topco 1", 1, None),
        ("M-Files MetaTiedot", 2, None), ("Esdec Solar", 1, None), ("IW Buyer", 1, None), ("KDC/ONE", 1, None),
        ("Uniti Group", 1, None), ("Iris Software", 1, None),
    ], "ads_excerpt.htm", "Real excerpt of the Apollo Debt Solutions BDC 10-Q, period end 2026-06-30 (0001193125-26-341358).")
    make_html_assisted("hps", [
        ("Arcfield Acquisition Corp", 2, None), ("Cadence - Southwick", 3, None), ("Titan BW Borrower", 3, None),
        ("Oak Funding", 2, None), ("Apex Group Treasury", 1, None), ("Netrisk Group Luxco", 2, None),
        ("Aryeh Bidco", 1, None), ("Enstall Group", 1, None), ("Thrasio Holdings", 1, None),
        ("ELNG Equity LLC", 2, None), ("ULTRA III", 1, None), ("Chord Searchlight", 1, None),
        ("Kpler Finance", 2, None), ("Peraton", 1, None),
    ], [("Sentinel Buyer", 1, None)], "hps_excerpt.htm",
        "Real excerpt of the HPS Corporate Lending Fund 10-Q, period end 2026-06-30 (0001628280-26-056772).")
    make_html_assisted("orcic", [
        ("DIRECTV Financing", 1, None), ("CoolSys", 1, None), ("Hg Genesis 9 SumoCo", 1, None),
        ("STS PARENT", 2, None), ("Horizon Avionics", 1, None), ("Jeppesen", 1, None),
        ("Plasma Buyer", 2, None), ("GT Silver", 1, None), ("WP Silver", 1, None), ("OCIC SLF LLC", 1, None),
        ("LSI Financing LLC", 1, None), ("Notorious Purchaser II", 1, None), ("Coupa Holdings", 1, None),
    ], [("LSI Financing LLC", 1, None)], "orcic_excerpt.htm",
        "Real excerpt of the Blue Owl Credit Income Corp. 10-Q, period end 2026-06-30 (0001812554-26-000047).")
    q1 = RAW / "ads_10q_2026-03-31.htm"
    if q1.exists():
        make_ads("ads", date(2026, 3, 31), [
            ("Corpuls Heartbeat", 2, None), ("IQN Holding", 2, None), ("Accel International", 2, None),
            ("ERC Topco", 2, None), ("Kaman", 2, None),
        ], "ads_q1_excerpt.htm", "Real excerpt of the Apollo Debt Solutions BDC 10-Q, period end 2026-03-31.")
    else:
        print("fixtures/raw/ads_10q_2026-03-31.htm not found: second period excerpt skipped")


if __name__ == "__main__":
    main()
