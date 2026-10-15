"""Day 1 read-only: parse Schedule of Investments HTML table for HPS and ORCIC.
No DB writes. Run: python -m pipeline.scout_html
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

from lxml import etree

RAW = Path(__file__).resolve().parent.parent / "fixtures" / "raw"
PE = "2026-06-30"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
_SCALE_RE = re.compile(r"\$?\s*\(?([\d,\.]+)\)?")
_DATE_RE   = re.compile(r"\b(\d{1,2}/\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4})\b")
_YEAR_RE   = re.compile(r"\b(20[2-4]\d)\b")


def _clean(s: str) -> str:
    return " ".join(s.split())


def _parse_num(s: str) -> Decimal | None:
    s = _clean(s)
    if not s or s in ("-", "—", "–", "N/A", ""):
        return None
    neg = s.startswith("(") and s.endswith(")")
    s2 = s.strip("()").replace(",", "").replace("$", "").strip()
    try:
        v = Decimal(s2)
        return -v if neg else v
    except InvalidOperation:
        return None


def _is_blank(s: str) -> bool:
    return _clean(s) in ("", "-", "—", "–", "N/A")


# ---------------------------------------------------------------------------
# Find the Schedule of Investments table(s)
# ---------------------------------------------------------------------------
def _find_soi_tables(root) -> list:
    """Return <table> elements that contain 'Schedule of Investments' header nearby."""
    candidates = []
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        tag = el.tag.split("}")[-1].lower()
        if tag not in ("table", "div"):
            continue
        text = _clean("".join(el.itertext()))
        if re.search(r"schedule of investments", text, re.I):
            if tag == "table":
                candidates.append(el)
    # deduplicate by element id
    seen, out = set(), []
    for t in candidates:
        if id(t) not in seen:
            seen.add(id(t))
            out.append(t)
    return out


# ---------------------------------------------------------------------------
# Row classification
# ---------------------------------------------------------------------------
INSTRUMENT_KEYWORDS = (
    "first lien", "second lien", "revolver", "revolving", "delayed draw",
    "subordinated", "senior secured", "unsecured", "mezzanine", "preferred",
    "common", "warrant", "equity", "lp interest", "llc interest",
    "membership", "ordinary shares", "term loan", "ddtl", "units",
    "partnership interest", "class", "notes",
)
TOTAL_KEYWORDS = ("total investments", "total portfolio", "net assets", "total assets",
                  "total debt", "subtotal", "total non-controlled", "total controlled",
                  "total affiliated", "total non-affiliated", "total first lien",
                  "total second lien", "total other")

AFFIL_KEYWORDS = ("non-controlled", "affiliated", "controlled affiliates",
                  "non-affiliated", "affiliated issuer")


def _classify_row(cells: list[str]) -> str:
    text = " ".join(cells).lower()
    if any(k in text for k in TOTAL_KEYWORDS):
        return "total"
    if any(k in text for k in AFFIL_KEYWORDS) and len([c for c in cells if not _is_blank(c)]) <= 2:
        return "header"
    if cells and any(k in cells[0].lower() for k in INSTRUMENT_KEYWORDS):
        return "instrument_header"
    return "data"


# ---------------------------------------------------------------------------
# Per-filer table parser
# ---------------------------------------------------------------------------
def parse_soi(label: str) -> list[dict]:
    """Parse Schedule of Investments HTML into a flat list of row dicts."""
    path = RAW / f"{label}_10q_{PE}.htm"
    tree = etree.parse(str(path), etree.XMLParser(huge_tree=True, recover=True))
    root = tree.getroot()
    tables = _find_soi_tables(root)
    print(f"  [{label}] SOI tables found: {len(tables)}")

    rows: list[dict] = []
    # We parse every table with SOI text and merge
    for tbl in tables:
        # Detect column headers from first rows
        header_cols: list[str] = []
        for tr in tbl.iter():
            if not isinstance(tr.tag, str) or tr.tag.split("}")[-1].lower() != "tr":
                continue
            cells = [_clean("".join(td.itertext())) for td in tr
                     if isinstance(td.tag, str) and td.tag.split("}")[-1].lower() in ("td", "th")]
            if not cells:
                continue
            low = " ".join(cells).lower()
            if "maturity" in low and ("spread" in low or "reference" in low or "par" in low or "principal" in low):
                header_cols = cells
                break

        # Now parse data rows
        current_affil = "unknown"
        current_section = ""
        in_soi = False
        for tr in tbl.iter():
            if not isinstance(tr.tag, str) or tr.tag.split("}")[-1].lower() != "tr":
                continue
            cells = [_clean("".join(td.itertext())) for td in tr
                     if isinstance(td.tag, str) and td.tag.split("}")[-1].lower() in ("td", "th")]
            if not cells:
                continue
            text = " ".join(cells).lower()

            # Start / end markers
            if re.search(r"schedule of investments", text, re.I):
                in_soi = True
                continue

            if not in_soi:
                continue

            # Section / affiliation header
            non_blank = [c for c in cells if not _is_blank(c)]
            if len(non_blank) <= 2:
                t = non_blank[0].lower() if non_blank else ""
                if any(k in t for k in ("non-affiliated", "controlled affiliates",
                                         "affiliated issuers", "non-controlled affiliates",
                                         "affiliated", "non-controlled")):
                    current_affil = non_blank[0]
                    continue
                if re.search(r"^(debt|equity|preferred|warrant|total|senior|first|second|mezzanine)", t):
                    current_section = non_blank[0]
                    continue

            # Total / subtotal rows
            kind = _classify_row(cells)

            # Detect column positions from header (best-effort: fixed order seen in these filings)
            # Column order (typical BDC): Company | RefRate&Spread | Rate | Maturity | Par/Units | Cost | FV [| %NA]
            n = len(cells)
            if n >= 6:
                name_col  = cells[0]
                # Find maturity: cell matching date pattern
                mat_col   = next((c for c in cells[1:] if _DATE_RE.search(c)), None)
                # Par/units: first numeric after date, or col[-3]
                # FV: last numeric (before %NA)
                # cost: second-to-last numeric
                nums = [i for i, c in enumerate(cells) if _parse_num(c) is not None]
                fv_idx   = nums[-1]   if nums else None
                cost_idx = nums[-2]   if len(nums) >= 2 else None
                par_idx  = nums[-3]   if len(nums) >= 3 else None
            else:
                name_col, mat_col, fv_idx, cost_idx, par_idx = cells[0] if cells else "", None, None, None, None
                nums = []

            # Detect instrument type in name cell or as a separate cell
            inst_type = None
            for kw in INSTRUMENT_KEYWORDS:
                if kw in (name_col or "").lower():
                    inst_type = name_col
                    name_col = ""
                    break

            row = {
                "label": label,
                "affil": current_affil,
                "section": current_section,
                "kind": kind,
                "name": name_col,
                "instrument_type": inst_type,
                "maturity": mat_col,
                "principal": _parse_num(cells[par_idx]) if par_idx is not None else None,
                "cost": _parse_num(cells[cost_idx]) if cost_idx is not None else None,
                "fair_value": _parse_num(cells[fv_idx]) if fv_idx is not None else None,
                "raw": cells,
            }
            rows.append(row)

    return rows


# ---------------------------------------------------------------------------
# Column-mapping approach: identify positions from header row
# ---------------------------------------------------------------------------
def parse_soi_v2(label: str) -> tuple[list[dict], dict]:
    """Smarter parser: find the header row in each table section, then parse under it."""
    path = RAW / f"{label}_10q_{PE}.htm"
    tree = etree.parse(str(path), etree.XMLParser(huge_tree=True, recover=True))
    root = tree.getroot()

    rows: list[dict] = []
    meta: dict = {"tables": 0, "header_rows_found": 0}

    affil_pat = re.compile(
        r"(non-?affiliated|controlled affiliates|non-?controlled|affiliated issuers?)", re.I)
    total_pat = re.compile(
        r"^total\b|^subtotal\b|net assets|total investments|total portfolio", re.I)

    for tbl in root.iter():
        if not isinstance(tbl.tag, str) or tbl.tag.split("}")[-1].lower() != "table":
            continue
        tbl_text = _clean("".join(tbl.itertext()))
        if not re.search(r"schedule of investments", tbl_text, re.I):
            continue
        meta["tables"] += 1

        # Gather all rows as cell-lists
        all_rows: list[list[str]] = []
        for tr in tbl.iter():
            if not isinstance(tr.tag, str) or tr.tag.split("}")[-1].lower() != "tr":
                continue
            cells = [_clean("".join(td.itertext())) for td in tr
                     if isinstance(td.tag, str) and td.tag.split("}")[-1].lower() in ("td", "th")]
            if cells:
                all_rows.append(cells)

        # Find header row(s): contain Maturity + (Cost or Amortized)
        hdr_indices = []
        for i, cells in enumerate(all_rows):
            low = " ".join(cells).lower()
            if "maturity" in low and ("cost" in low or "amortized" in low or "par" in low):
                hdr_indices.append(i)
                meta["header_rows_found"] += 1

        if not hdr_indices:
            continue

        # Map column positions from first header row
        hdr = all_rows[hdr_indices[0]]
        col = {}
        for j, h in enumerate(hdr):
            hl = h.lower()
            if "company" in hl or "portfolio" in hl or hl == "":
                col.setdefault("name", j)
            elif "maturity" in hl:
                col["maturity"] = j
            elif "par" in hl or "principal" in hl or "units" in hl:
                col["principal"] = j
            elif "amortized" in hl or ("cost" in hl and "fair" not in hl):
                col["cost"] = j
            elif "fair" in hl or "value" in hl:
                col["fair_value"] = j
            elif "spread" in hl or "reference" in hl:
                col["spread"] = j
            elif "interest" in hl or "rate" in hl:
                col["rate"] = j

        start = hdr_indices[0] + 1
        current_affil = "Non-Affiliated"
        current_section = ""
        current_inst = ""

        for cells in all_rows[start:]:
            non_blank = [c for c in cells if not _is_blank(c)]
            row_text = " ".join(cells)
            low = row_text.lower()

            # Affiliation section header: 1-2 non-blank cells, affil keyword
            if len(non_blank) <= 2 and affil_pat.search(row_text):
                current_affil = non_blank[0] if non_blank else current_affil
                continue

            # Total / subtotal row
            is_total = bool(total_pat.search(non_blank[0] if non_blank else ""))

            # Instrument-type-only row: the cell is entirely an instrument keyword
            if len(non_blank) == 1 and any(k in low for k in INSTRUMENT_KEYWORDS):
                current_inst = non_blank[0]
                continue

            # Skip blank rows
            if not non_blank:
                continue

            # Extract fields using column map
            def cell(k):
                j = col.get(k)
                return cells[j] if j is not None and j < len(cells) else ""

            name_raw = cell("name")
            # If name looks like an instrument type, treat it as section
            if name_raw and any(k in name_raw.lower() for k in INSTRUMENT_KEYWORDS) and not cell("fair_value"):
                current_inst = name_raw
                continue

            mat  = cell("maturity") or None
            if mat and not _DATE_RE.search(mat) and not _YEAR_RE.search(mat):
                mat = None

            prin = _parse_num(cell("principal"))
            cost = _parse_num(cell("cost"))
            fv   = _parse_num(cell("fair_value"))

            rows.append({
                "label":           label,
                "affil":           current_affil,
                "section":         current_section,
                "instrument_type": current_inst,
                "kind":            "total" if is_total else "data",
                "name":            name_raw,
                "maturity":        mat,
                "principal":       prin,
                "cost":            cost,
                "fair_value":      fv,
                "raw":             cells,
            })

    return rows, meta


# ---------------------------------------------------------------------------
# Join HTML rows to XBRL rows
# ---------------------------------------------------------------------------
def join_html_xbrl(html_rows: list[dict], xbrl_rows: list[dict]) -> dict:
    """Match on (principal, cost, fair_value) rounded to thousands."""
    def key(r, scale=1000):
        def rnd(v):
            if v is None:
                return None
            return int(round(float(v) / scale))
        return (rnd(r.get("principal")), rnd(r.get("cost")), rnd(r.get("fair_value")))

    xbrl_by_key: dict = defaultdict(list)
    for r in xbrl_rows:
        if r.get("principal") is not None or r.get("fair_value") is not None:
            xbrl_by_key[key(r)].append(r)

    matched_html = 0
    multi_match  = 0
    matched_xbrl = set()

    for hr in html_rows:
        if hr["kind"] == "total" or (hr["principal"] is None and hr["fair_value"] is None):
            continue
        k = key(hr)
        hits = xbrl_by_key.get(k, [])
        if hits:
            matched_html += 1
            if len(hits) > 1:
                multi_match += 1
            for h in hits:
                matched_xbrl.add(id(h))

    html_data = [r for r in html_rows if r["kind"] != "total" and
                 (r["principal"] is not None or r["fair_value"] is not None)]
    xbrl_data = [r for r in xbrl_rows if r.get("principal") is not None]

    return {
        "html_data_rows":  len(html_data),
        "matched_html":    matched_html,
        "multi_match":     multi_match,
        "xbrl_with_prin":  len(xbrl_data),
        "matched_xbrl":    len(matched_xbrl),
        "unmatched_xbrl":  len(xbrl_data) - len(matched_xbrl),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    from pipeline.ixbrl import parse_ixbrl, assemble_investments, split_pipe_identifier, INVESTMENT_TAGS
    FV_TAG   = INVESTMENT_TAGS["fair_value"]
    COST_TAG = INVESTMENT_TAGS["cost"]
    PRIN_TAG = INVESTMENT_TAGS["principal"]
    IDAX = "us-gaap:InvestmentIdentifierAxis"

    for label in ("hps_corporate_lending", "blue_owl_credit_income"):
        print(f"\n{'='*70}")
        print(f"FILER: {label}")
        print(f"{'='*70}")

        # --- HTML parse ---
        html_rows, meta = parse_soi_v2(label)
        print(f"\n[HTML] tables={meta['tables']}  header_rows={meta['header_rows_found']}")

        data_rows   = [r for r in html_rows if r["kind"] == "data"]
        total_rows  = [r for r in html_rows if r["kind"] == "total"]
        with_fv     = [r for r in data_rows if r["fair_value"] is not None]
        with_prin   = [r for r in data_rows if r["principal"] is not None]

        print(f"HTML rows: total={len(html_rows)}  data={len(data_rows)}  "
              f"with_fv={len(with_fv)}  with_prin={len(with_prin)}  totals={len(total_rows)}")

        # Affiliation breakdown
        affil_fv = defaultdict(Decimal)
        for r in total_rows:
            if r["fair_value"] is not None and r["name"]:
                affil_fv[r["name"]] += r["fair_value"]
        print("\nTotal rows printed in table:")
        for name, fv in sorted(affil_fv.items(), key=lambda x: -abs(x[1]))[:12]:
            print(f"  {name[:70]:<70}  {fv:>20,.0f}")

        # Section headers / subtotals
        affil_counts = Counter(r["affil"] for r in data_rows)
        print("\nAffiliation section counts (data rows):", dict(affil_counts.most_common(8)))

        inst_counts = Counter(r["instrument_type"] for r in data_rows if r["instrument_type"])
        print("Instrument type counts:", dict(inst_counts.most_common(10)))

        # 5 sample rows
        print("\n5 sample data rows:")
        for r in with_prin[:5]:
            print(f"  affil={r['affil'][:25]!r}  inst={r['instrument_type']!r}  "
                  f"mat={r['maturity']!r}  prin={r['principal']}  cost={r['cost']}  fv={r['fair_value']}")
            print(f"    name={r['name'][:80]!r}")

        # Missing maturity by instrument type
        no_mat = [r for r in data_rows if r["maturity"] is None and r["fair_value"] is not None]
        no_mat_inst = Counter(r["instrument_type"] for r in no_mat)
        print(f"\nRows missing maturity: {len(no_mat)} / {len(with_fv)}")
        print("  by instrument type:", dict(no_mat_inst.most_common(10)))

        # --- XBRL parse ---
        ctxs, facts, texts = parse_ixbrl(RAW / f"{label}_10q_{PE}.htm")
        kw = {} if label == "ads" else {"identifier_parser": split_pipe_identifier}
        xbrl_rows = assemble_investments(ctxs, facts, texts, PE, **kw)

        # XBRL schedule row FV sum
        xbrl_by_id = {}
        for f in facts:
            c = ctxs.get(f.context_ref)
            if c and c.instant == PE and IDAX in c.typed and len(c.dims) == 1:
                xbrl_by_id.setdefault(c.typed[IDAX], {})[f.name] = (
                    xbrl_by_id.get(c.typed[IDAX], {}).get(f.name) or f.value)
        xbrl_sched = {i: t for i, t in xbrl_by_id.items() if FV_TAG in t or COST_TAG in t}
        xbrl_fv_sum = sum((t.get(FV_TAG) or Decimal(0)) for t in xbrl_sched.values())

        # Filing undimensioned total at PE
        filing_total = next((f.value for f in facts
                             if f.name == FV_TAG and f.value is not None
                             and ctxs.get(f.context_ref)
                             and not ctxs[f.context_ref].dims
                             and ctxs[f.context_ref].instant == PE), None)

        # HTML total rows: find "total investments" line
        html_total_fv = next(
            (r["fair_value"] for r in reversed(total_rows)
             if r["fair_value"] and r["name"] and
             re.search(r"total investments|total portfolio", r["name"], re.I)),
            None)
        if html_total_fv is None:
            # fallback: largest positive total
            cands = sorted([r for r in total_rows if r["fair_value"] and r["fair_value"] > 0],
                           key=lambda r: r["fair_value"], reverse=True)
            html_total_fv = cands[0]["fair_value"] if cands else None

        print(f"\n[RECONCILE]")
        print(f"  HTML printed total investments FV : {html_total_fv}")
        print(f"  XBRL schedule row FV sum          : {xbrl_fv_sum:,.0f}")
        print(f"  XBRL undimensioned total at PE    : {filing_total}")
        if html_total_fv and filing_total:
            print(f"  HTML vs filing total gap          : {html_total_fv - filing_total:,.0f}")
        if filing_total:
            print(f"  XBRL sched vs filing total gap    : {xbrl_fv_sum - filing_total:,.0f}")

        # Per-affiliation totals from HTML
        print("\n  Affiliation totals from HTML total rows:")
        for r in total_rows:
            if r["fair_value"] and r["name"]:
                print(f"    {r['name'][:60]:<60}  fv={r['fair_value']:>18,.0f}")

        # --- Join ---
        join = join_html_xbrl(data_rows, xbrl_rows)
        print(f"\n[JOIN] html_data={join['html_data_rows']}  matched={join['matched_html']}  "
              f"multi_match={join['multi_match']}  xbrl_with_prin={join['xbrl_with_prin']}  "
              f"xbrl_matched={join['matched_xbrl']}  xbrl_unmatched={join['unmatched_xbrl']}")

        # --- ORCIC dup check ---
        if label == "blue_owl_credit_income":
            print("\n[ORCIC DUPLICATE PAIRS in HTML]")
            DUP_FRAGS = [
                "LSI Financing LLC",
                "Fifth Season Investments",
                "OCIC SLF",
                "Blue Owl Credit SLF",
                "Blue Owl Cross-Strategy Opportunities 2025-1",
                "OWL-HP FINANCE",
                "Wingspire Capital Holdings",
            ]
            for frag in DUP_FRAGS:
                hits = [r for r in data_rows if frag.lower() in (r["name"] or "").lower()]
                print(f"  {frag[:50]:<50}: {len(hits)} HTML rows  "
                      f"FVs={[r['fair_value'] for r in hits]}")

        # --- HPS special rows ---
        if label == "hps_corporate_lending":
            print("\n[HPS SPECIAL ROWS]")
            for name_frag in ("Apex Group", "Oak Funding"):
                hits = [r for r in html_rows if name_frag.lower() in (r["name"] or "").lower()]
                for h in hits:
                    print(f"  {name_frag}: kind={h['kind']}  affil={h['affil']!r}  "
                          f"inst={h['instrument_type']!r}  mat={h['maturity']!r}  "
                          f"prin={h['principal']}  fv={h['fair_value']}  name={h['name'][:80]!r}")


if __name__ == "__main__":
    main()
