"""Reader for the main Schedule of Investments table in the filing HTML.

Used by the HTML-assisted adapters (HPS, ORCIC): the XBRL has no maturity for them, and HPS has
no row level type, so the printed table supplies maturity, section, industry and the rate text.

Amounts are kept only for the join key (thousands as printed). A printed dash is None here:
it is empty in the key and is never stored or turned into a zero.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

from lxml import etree

CURRENCY_CELLS = {"$", "€", "£", "C$", "A$", "NZ$", "S$", "kr", "¥", "₩", "CHF", "DKK", "NOK", "SEK"}
AMOUNT_RE = re.compile(r"^\(?\d{1,3}(,\d{3})*\)?$|^\(?\d+\)?$")
DATE_RE = re.compile(r"^(\d{1,2}/\d{1,2}/\d{4}|\d{1,2}/\d{4})$")
RATE_REF_RE = re.compile(r"^[A-Z]{1,4}\s*\+$|^N/A$|^Fixed$|^[A-Z]{1,6}$")
FOOTNOTE_MARKERS_RE = re.compile(r"\s*(?:\(\d{1,3}\))+")
DASHES = {"—", "–", "-"}
TYPE_WORDS = ("lien", "loan", "stock", "interest", "equity", "facility", "notes", "shares",
              "warrant", "units", "preferred", "debt", "revolver", "term")


@dataclass
class HtmlRow:
    order: int
    name_html: str
    name: str                    # name_html without footnote markers such as (4)(8)
    section: str | None
    affil: str | None
    industry: str | None
    maturity: str | None         # as printed: m/d/yyyy (HPS) or m/yyyy (ORCIC)
    instrument_cell: str | None  # row level type text when the table prints one (ORCIC)
    rate_tokens: list[str]       # printed tokens between the type (or name) and the maturity
    principal: Decimal | None    # thousands as printed; None when blank or a dash (join key only)
    cost: Decimal | None
    fair_value: Decimal | None
    amount_cells: int = 0        # printed amount cells including dashes; 0 means no amounts on the row
    tokens: list[str] = field(default_factory=list)
    element: object = None       # the <tr> this row came from (used only to build test excerpts)
    header_elements: tuple = ()  # the affiliation, section and industry <tr> in force for the row
    principal_symbol: str | None = None   # the currency cell printed right before the principal amount, as printed


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


def _first_cell(table) -> str:
    for tr in table.iter():
        if _ln(tr) == "tr":
            cells = [c for c in _row_cells(tr) if c]
            if cells:
                return cells[0]
    return ""


def main_schedule_tables(root) -> list:
    """The first contiguous run of tables whose first cell starts with 'Company' is the schedule at the
    period end. The comparative schedule and the unfunded commitment tables come later."""
    tabs = [e for e in root.iter() if _ln(e) == "table"]
    i = 0
    while i < len(tabs) and not _first_cell(tabs[i]).startswith("Company"):
        i += 1
    out = []
    while i < len(tabs) and _first_cell(tabs[i]).startswith("Company"):
        out.append(tabs[i])
        i += 1
    return out


def parse_main_schedule(path: Path, amounts_after_maturity: int,
                        par_on_rows_without_maturity: bool, root=None) -> list[HtmlRow]:
    if root is None:
        root = etree.parse(str(path), etree.XMLParser(huge_tree=True, recover=True)).getroot()
    rows: list[HtmlRow] = []
    ctx = {"affil": None, "section": None, "industry": None}
    ctx_tr: dict = {"affil": None, "section": None, "industry": None}
    for table in main_schedule_tables(root):
        for tr in table.iter():
            if _ln(tr) != "tr":
                continue
            cells = [c for c in _row_cells(tr) if c]
            toks = [c for c in cells if c not in CURRENCY_CELLS and c != "%"]
            if not toks:
                continue
            first = toks[0]
            if first.startswith(("Company(", "Ref. Rate")) or first.lower().startswith("total"):
                continue
            if len(toks) == 1:
                low = first.lower()
                if "controlled" in low or "affiliated" in low:
                    ctx["affil"], ctx_tr["affil"] = first, tr
                elif re.search(r"(debt|equity|joint venture|investments)", low) and len(first) < 50:
                    ctx["section"], ctx_tr["section"] = first, tr
                else:
                    ctx["industry"], ctx_tr["industry"] = first, tr
                continue
            if _num(first) is not None and all(_num(x) is not None or x in DASHES or "." in x for x in toks):
                continue  # unlabelled industry subtotal
            mat_i = next((i for i, x in enumerate(toks) if i > 0 and DATE_RE.match(x)), None)
            tail = toks[(mat_i + 1 if mat_i is not None else 1):]
            if mat_i is None:
                tail = [x for x in tail if x != "N/A"]
            amts = [(_num(x) if x not in DASHES else None) for x in tail if _num(x) is not None or x in DASHES]
            inst = next((x for x in toks[1:] if not DATE_RE.match(x) and not RATE_REF_RE.match(x)
                         and _num(x) is None and any(w in x.lower() for w in TYPE_WORDS) and "%" not in x), None)
            n = len(amts)
            need = amounts_after_maturity
            has_par = mat_i is not None or par_on_rows_without_maturity
            principal = amts[-need] if (n >= need and has_par) else None
            cost = amts[-2] if n >= 2 else None
            fv = amts[-1] if n >= 1 else None
            symbol = None
            if principal is not None or (n >= need and has_par):
                # the currency cell printed right before the principal amount cell, if any
                m_ci = next((i for i, x in enumerate(cells) if i > 0 and DATE_RE.match(x)), None)
                amt_ci = [i for i, x in enumerate(cells) if i > (m_ci if m_ci is not None else 0)
                          and (_num(x) is not None or x in DASHES)]
                if len(amt_ci) >= need and amt_ci[-need] > 0 and cells[amt_ci[-need] - 1] in CURRENCY_CELLS:
                    symbol = cells[amt_ci[-need] - 1]
            rate_start = (toks.index(inst) + 1) if inst is not None else 1
            rate_tokens = toks[rate_start:mat_i] if mat_i is not None else []
            rows.append(HtmlRow(
                order=len(rows), name_html=first, name=FOOTNOTE_MARKERS_RE.sub("", first).strip(),
                section=ctx["section"], affil=ctx["affil"], industry=ctx["industry"],
                maturity=toks[mat_i] if mat_i is not None else None, instrument_cell=inst,
                rate_tokens=rate_tokens, principal=principal, cost=cost, fair_value=fv, amount_cells=n,
                tokens=toks, element=tr,
                header_elements=(ctx_tr["affil"], ctx_tr["section"], ctx_tr["industry"]),
                principal_symbol=symbol))
    return rows


# ---------------------------------------------------------------------------------------------------
# ADS: the schedule prints the industry, the company group and the legal name separately. The XBRL
# identifier runs them together ('<industry> <group> <legal name>'), so the legal name is read here.
#   industry header (single cell, one of the printed 'Total <industry>' names)
#   company group header (any other single cell)
#   company row   [legal name, type, rate, maturity, par, cost, fair value, footnote markers]
#   tranche rows  [type, rate, maturity, par, cost, fair value, footnote markers] (legal name inherited)
# ---------------------------------------------------------------------------------------------------
@dataclass
class AdsHtmlRow:
    order: int
    industry: str | None
    group: str | None
    legal_name: str | None
    type_text: str
    rate_text: str | None
    maturity: str | None
    principal: Decimal | None   # thousands as printed; a dash or blank is None (join key only)
    cost: Decimal | None
    fair_value: Decimal | None
    amount_cells: int
    element: object = None
    header_elements: tuple = ()  # industry, group and company <tr> in force, for building test excerpts


_CURRENCY_PREFIX = re.compile(r"^(?:[$€£¥₩]|[A-Za-z]{1,4}\$?)\s*(?=[\d(])")


def _ads_amount(tok: str) -> tuple[bool, Decimal | None]:
    """An amount cell: digits with an optional currency prefix ('$', 'Skr 614,359') and an optional share or
    unit suffix ('82,735 Shares'). A dash is an amount cell with no value."""
    t = tok.strip()
    if t in DASHES:
        return True, None
    core = re.sub(r"\s*(?:Shares|Units)$", "", _CURRENCY_PREFIX.sub("", t), flags=re.I)
    if AMOUNT_RE.match(core):
        return True, _num(core)
    return False, None


def parse_ads_schedule(path: Path, industries: set[str], stems: list[str], root=None) -> list[AdsHtmlRow]:
    if root is None:
        root = etree.parse(str(path), etree.XMLParser(huge_tree=True, recover=True)).getroot()
    tables = [e for e in root.iter() if _ln(e) == "table"]
    run, i = [], 0
    while i < len(tables) and not _first_cell(tables[i]).startswith("Industry/Company"):
        i += 1
    while i < len(tables) and _first_cell(tables[i]).startswith("Industry/Company"):
        run.append(tables[i])
        i += 1
    rows: list[AdsHtmlRow] = []
    industry = group = legal = None
    tr_industry = tr_group = tr_legal = None
    for table in run:
        for tr in table.iter():
            if _ln(tr) != "tr":
                continue
            toks = [c for c in _row_cells(tr) if c and c not in CURRENCY_CELLS and c != "%"]
            if not toks or toks[0].startswith("Industry/Company") or toks[0].lower().startswith("total"):
                continue
            if len(toks) == 1:
                if toks[0] in industries:
                    industry, tr_industry, group, legal, tr_group, tr_legal = toks[0], tr, None, None, None, None
                else:
                    group, tr_group, legal, tr_legal = toks[0], tr, None, None
                continue
            if all(_ads_amount(x)[0] for x in toks):
                continue  # a subtotal line
            if any(toks[0].startswith(s) for s in stems):
                type_idx = 0
            elif len(toks) > 1 and any(toks[1].startswith(s) for s in stems):
                type_idx = 1
                legal, tr_legal = toks[0], tr
            else:
                continue
            rest = toks[type_idx + 1:]
            amounts, k = [], 2
            while k < len(rest) and len(amounts) < 3 and _ads_amount(rest[k])[0]:
                amounts.append(_ads_amount(rest[k])[1])
                k += 1
            rows.append(AdsHtmlRow(
                order=len(rows), industry=industry, group=group, legal_name=legal, type_text=toks[type_idx],
                rate_text=rest[0] if rest else None, maturity=rest[1] if len(rest) > 1 else None,
                principal=amounts[0] if len(amounts) == 3 else None,
                cost=amounts[-2] if len(amounts) >= 2 else None, fair_value=amounts[-1] if amounts else None,
                amount_cells=len(amounts), element=tr, header_elements=(tr_industry, tr_group, tr_legal)))
    return rows
