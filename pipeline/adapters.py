"""Per-filer adapters: FilerAdapter.parse(filing) -> raw_holdings rows (phase_wise.md Phase 3).

Every adapter returns tuples in the raw_holdings insert order:
  (portfolio_company_raw, industry_raw, instrument_type_raw, interest_rate_raw, maturity_date_raw,
   principal_raw, principal_unit_raw, cost_raw, fair_value_raw, footnotes_raw, row_order, source_url)
Values are kept as parsed, as text. NUMERIC strings are plain decimals in dollars with no exponent.
Nothing is converted, excluded or defaulted here: exclusion happens later in normalize.

Tag maps and footnote patterns come from the filers section of config.yaml.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from lxml import etree

from pipeline import ixbrl as X
from pipeline.html_schedule import AdsHtmlRow, HtmlRow, parse_ads_schedule, parse_main_schedule
from pipeline.normalize import collapse_repeated_prefix, strip_industry_prefix
from pipeline.ixbrl import (IDENTIFIER_AXIS, NS_IX, assemble_investments, parse_ixbrl,
                            split_pipe_identifier)

RawRow = tuple


@dataclass
class Filing:
    label: str
    cik: str
    edgar_name: str
    period_end: date
    path: Path
    source_url: str
    accession: str


def plain(value: Decimal | None) -> str | None:
    """Decimal as plain text with no exponent, as parsed. None stays None."""
    return None if value is None else format(value, "f")


def unit_text(row: dict) -> str | None:
    return row["principal_unit"] if row["principal"] is not None else None


def linked_footnotes(path: Path, contexts: dict, facts: list, period_end: str) -> dict[str, list[str]]:
    """Footnote texts (ix:footnote linked by ix:relationship) of each investment identifier at period_end."""
    root = etree.parse(str(path), etree.XMLParser(huge_tree=True, recover=True)).getroot()
    notes = {el.get("id"): " ".join("".join(el.itertext()).split())
             for el in root.iter(f"{{{NS_IX}}}footnote")}
    fact_notes: dict[str, set[str]] = {}
    for rel in root.iter(f"{{{NS_IX}}}relationship"):
        for src in (rel.get("fromRefs") or "").split():
            fact_notes.setdefault(src, set()).update((rel.get("toRefs") or "").split())
    elements = list(root.iter(f"{{{NS_IX}}}nonFraction"))
    if len(elements) != len(facts):
        raise RuntimeError("nonFraction element count differs from parsed facts")
    out: dict[str, set[str]] = {}
    for el, fact in zip(elements, facts):
        fid = el.get("id")
        if not fid or fid not in fact_notes:
            continue
        c = contexts.get(fact.context_ref)
        if c and c.instant == period_end and IDENTIFIER_AXIS in c.typed and len(c.dims) == 1:
            out.setdefault(c.typed[IDENTIFIER_AXIS], set()).update(
                notes[n] for n in fact_notes[fid] if n in notes)
    return {k: sorted(v) for k, v in out.items()}


class FilerAdapter(ABC):
    """parse(filing) -> rows. `stats` collects counts that the ingest logs and the report can cite."""

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.stats: Counter = Counter()

    @abstractmethod
    def parse(self, filing: Filing) -> list[RawRow]:
        ...

    def load_xbrl(self, filing: Filing, identifier_parser=None):
        pe = filing.period_end.isoformat()
        contexts, facts, text_facts = parse_ixbrl(filing.path)
        kw = {"tags": self.cfg["tags"], "text_tags": self.cfg["text_tags"]}
        if identifier_parser is not None:
            kw["identifier_parser"] = identifier_parser
        rows = assemble_investments(contexts, facts, text_facts, pe, **kw)
        schedule = [r for r in rows if r["fair_value"] is not None or r["cost"] is not None]
        return contexts, facts, text_facts, schedule


# ---------------------------------------------------------------------------
# ADS: one typed identifier per row, '<industry> <name> Investment Type <type> Interest Rate <rate>
# Maturity Date <date>'. 32 identifiers (2026-06-30) lack the 'Investment Type' token.
# ---------------------------------------------------------------------------
TYPE_TOKEN = re.compile(r"\s+Investment Type\s+")
RATE_MARK = re.compile(r"\s+Interest Rate\s+")
MATURITY_MARK = re.compile(r"\s+Maturity Date\s+")


def _tail(rest: str) -> tuple[str, str | None, str | None]:
    """Split '<text> Interest Rate <rate> Maturity Date <date>' into (text, rate, maturity)."""
    maturity = rate = None
    m = MATURITY_MARK.search(rest)
    if m:
        maturity = rest[m.end():].strip() or None
        rest = rest[: m.start()]
    m = RATE_MARK.search(rest)
    if m:
        rate = rest[m.end():].strip() or None
        rest = rest[: m.start()]
    return rest.strip(), rate, maturity


GLUED_TOKEN = re.compile(r"Investment Type\s+")          # token with no space before it ('Inc.Investment Type')
DASH_SPLIT = re.compile(r"\s*[-–]")                      # hyphen and en dash both occur in the filing
# first rate-like token: 'S+475', 'E+525', 'STIBOR+425', 'SONIA+300', '10.00%'
RATE_TOKEN = re.compile(r"(?<![A-Z])(?:[A-Z]{1,6}\+\s*\d|\d+(?:\.\d+)?%)")


def _split_rate_from_type(text: str) -> tuple[str, str | None]:
    """When the filing prints the rate straight after the type with no 'Interest Rate' label."""
    m = RATE_TOKEN.search(text)
    if not m or m.start() == 0:
        return text.strip(), None
    return text[: m.start()].strip(), text[m.start():].strip()


def ads_industry_names(path: Path) -> set[str]:
    """Industry names printed in the schedule: the 'Total <industry>' rows of the tables at the period end
    (the first contiguous run of tables whose first cell is 'Industry/Company')."""
    root = etree.parse(str(path), etree.XMLParser(huge_tree=True, recover=True)).getroot()
    ln = lambda e: e.tag.split("}")[-1].lower() if isinstance(e.tag, str) else ""  # noqa: E731

    def rows(table):
        for tr in table.iter():
            if ln(tr) == "tr":
                cells = [c for c in (" ".join("".join(td.itertext()).split()) for td in tr if ln(td) in ("td", "th")) if c]
                if cells:
                    yield cells

    tables = [e for e in root.iter() if ln(e) == "table"]
    first = lambda t: next(rows(t), [""])[0]  # noqa: E731
    i = 0
    while i < len(tables) and not first(tables[i]).startswith("Industry/Company"):
        i += 1
    names: set[str] = set()
    while i < len(tables) and first(tables[i]).startswith("Industry/Company"):
        for cells in rows(tables[i]):
            if cells[0].startswith("Total ") and not cells[0].startswith("Total Investments"):
                names.add(cells[0][len("Total "):])
        i += 1
    return names


class AdsAdapter(FilerAdapter):
    """Typed identifiers: '<industry> <name> Investment Type <type> Interest Rate <rate> Maturity Date <date>'.

    32 identifiers (2026-06-30) lack ' Investment Type '. Fallback 1 parses their text deterministically:
    the type starts at a class stem learned from the typed rows (First Lien Secured Debt, Common Equity,
    ...) and runs to the rate or maturity label. Fallback 2 takes the maturity from the XBRL text fact.
    A row with no stem keeps type NULL: no type is invented."""

    def prepare(self, filing: Filing) -> dict:
        """XBRL schedule rows, the printed table rows and the join between them (identifier -> table row)."""
        pe = filing.period_end.isoformat()
        contexts, facts, text_facts, schedule = self.load_xbrl(filing)
        typed = [r for r in schedule if TYPE_TOKEN.search(r["identifier"])]
        stems = sorted({DASH_SPLIT.split(_tail(TYPE_TOKEN.split(r["identifier"], maxsplit=1)[1])[0])[0].strip()
                        for r in typed}, key=len, reverse=True)
        stems = [s for s in stems if s]
        industries = ads_industry_names(filing.path)
        html_rows = parse_ads_schedule(filing.path, industries, stems)
        return {"pe": pe, "contexts": contexts, "facts": facts, "text_facts": text_facts, "schedule": schedule,
                "stems": stems, "industries": industries, "html_rows": html_rows,
                "html_for": self.join_html(schedule, html_rows)}

    def join_html(self, schedule: list[dict], html_rows: list[AdsHtmlRow]) -> dict[str, AdsHtmlRow]:
        """Join table rows to XBRL rows in thousands. Pass 1 uses (principal, cost, fair value). Pass 2 uses
        (cost, fair value) only, because equity rows print a share count in the par column that the XBRL
        does not carry as a principal. A dash or a missing fact is empty on both sides of the key only."""
        def k3(x):
            return _key(x["principal"], x["cost"], x["fair_value"])

        def k2(x):
            return _key(None, x["cost"], x["fair_value"])

        used: set[int] = set()
        found: dict[int, int] = {}
        for label, kx, kh in (("strict", k3, lambda h: _key(h.principal, h.cost, h.fair_value, 1000)),
                              ("relaxed", k2, lambda h: _key(None, h.cost, h.fair_value, 1000))):
            index: dict[tuple, list[int]] = defaultdict(list)
            for i, x in enumerate(schedule):
                if i not in used:
                    index[kx(x)].append(i)
            for h in html_rows:
                if h.order in found or h.amount_cells == 0:
                    continue
                cands = [i for i in index.get(kh(h), []) if i not in used]
                if not cands:
                    continue
                if len(cands) > 1:
                    self.stats[f"html_join_{label}_multi_candidates"] += 1
                    full = _alnum((h.industry or "") + (h.group or "") + (h.legal_name or ""))
                    same = [i for i in cands if _alnum(schedule[i]["raw_name"]).startswith(full)]
                    if same:
                        cands = same
                        self.stats[f"html_join_{label}_resolved_by_name"] += 1
                    else:
                        self.stats[f"html_join_{label}_resolved_by_order_unexplained"] += 1
                used.add(cands[0])
                found[h.order] = cands[0]
                self.stats[f"html_join_{label}"] += 1
        self.stats["html_rows"] = len(html_rows)
        self.stats["html_rows_without_amounts_or_match"] = len(html_rows) - len(found)
        self.stats["xbrl_rows_without_html_row"] = len(schedule) - len(used)
        by_order = {h.order: h for h in html_rows}
        return {schedule[i]["identifier"]: by_order[o] for o, i in found.items()}

    def parse(self, filing: Filing) -> list[RawRow]:
        prep = self.prepare(filing)
        pe, contexts, facts, text_facts, schedule = (prep[k] for k in ("pe", "contexts", "facts", "text_facts", "schedule"))
        stems, industries, html_for = prep["stems"], prep["industries"], prep["html_for"]
        notes = linked_footnotes(filing.path, contexts, facts, pe)

        mat_tag = self.cfg["text_tags"]["maturity"]
        text_maturity: dict[str, str] = {}
        for name, ref, text in text_facts:
            c = contexts.get(ref)
            if name == mat_tag and c and c.instant == pe and IDENTIFIER_AXIS in c.typed and text:
                text_maturity.setdefault(c.typed[IDENTIFIER_AXIS], text)

        aliases = self.cfg.get("industry_aliases") or {}
        prefixes = sorted(industries | set(aliases), key=len, reverse=True)
        self.stats["industry_names_in_table"] = len(industries)
        self.unmatched_industry: list[str] = []

        out: list[RawRow] = []
        for order, r in enumerate(schedule, start=1):
            ident = r["identifier"]
            industry = None
            for pre in prefixes:
                if ident.startswith(pre + " "):
                    industry = aliases.get(pre, pre)
                    self.stats["industry_by_alias" if pre in aliases else "industry_by_prefix"] += 1
                    break
            if industry is None:
                self.stats["industry_none"] += 1
                self.unmatched_industry.append(ident)
            if TYPE_TOKEN.search(ident):
                name, rest = TYPE_TOKEN.split(ident, maxsplit=1)
                inst, rate, maturity = _tail(rest)
                fallback1 = False
            else:
                fallback1 = True
                self.stats["no_investment_type_token"] += 1
                g = GLUED_TOKEN.search(ident)
                if g:
                    self.stats["token_glued_to_name"] += 1
                    name, rest = ident[: g.start()], ident[g.end():]
                    inst, rate, maturity = _tail(rest)
                else:
                    head, rate, maturity = _tail(ident)
                    name, inst = head, None
                    for idx in sorted(m.start() for s in stems for m in re.finditer(re.escape(s), head) if m.start() > 0):
                        name, inst = head[:idx].strip(), head[idx:].strip()
                        break
            inst = inst or None
            if inst and rate is None:
                inst, split_rate = _split_rate_from_type(inst)
                if split_rate:
                    rate = split_rate
                    self.stats["rate_found_after_type_text"] += 1
            if fallback1:
                self.stats["fallback_name_piece_type"] += 1 if inst else 0
                self.stats["fallback_name_piece_rate"] += 1 if rate else 0
                self.stats["fallback_name_piece_maturity"] += 1 if maturity else 0
            if maturity is None and ident in text_maturity:
                maturity = text_maturity[ident]
                self.stats["fallback_xbrl_text_fact_maturity"] += 1
            if inst is None:
                self.stats["still_no_type"] += 1
            if maturity is None:
                self.stats["still_no_maturity"] += 1
            if rate is None:
                self.stats["still_no_rate"] += 1
            h = html_for.get(ident)
            if h is not None and h.legal_name:
                name = h.legal_name                       # the printed legal name, without industry or group
                self.stats["name_from_html_table"] += 1
            else:                                         # no table row: drop the industry prefix and a repeated phrase
                name = collapse_repeated_prefix(strip_industry_prefix(name.strip(), industry))
                self.stats["name_from_xbrl_fallback"] += 1
            out.append((name.strip(), industry, inst, rate, maturity,
                        plain(r["principal"]), unit_text(r), plain(r["cost"]), plain(r["fair_value"]),
                        " | ".join(notes.get(ident, [])) or None, order, filing.source_url))
        self.stats["rows"] = len(out)
        return out


# ---------------------------------------------------------------------------
# HTML assisted adapters (HPS, ORCIC): XBRL supplies the numbers, the main schedule table supplies
# maturity, section, industry and rate text. Rows are joined on (principal, cost, fair value) in
# thousands. A dash or a missing XBRL fact is empty on both sides of the key only.
# ---------------------------------------------------------------------------
def _key(principal, cost, fair_value, scale: int = 1) -> tuple[int, int, int]:
    return tuple(int((v or Decimal(0)) * scale) for v in (principal, cost, fair_value))  # type: ignore[return-value]


def _alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.lower())


class HtmlAssistedAdapter(FilerAdapter):
    def identifier_parser(self):
        return split_pipe_identifier

    def rate_text(self, html: HtmlRow) -> str | None:
        raise NotImplementedError

    def pick_name(self, x: dict, html: HtmlRow) -> str:
        raise NotImplementedError

    def pick_instrument(self, x: dict, html: HtmlRow) -> str | None:
        raise NotImplementedError

    def maturity_text(self, html: HtmlRow) -> str | None:
        return html.maturity

    def match(self, filing: Filing):
        """Join the XBRL schedule rows to the main schedule table. Returns (pairs, dropped, notes) where
        pairs are (HtmlRow, xbrl row) in table order and dropped are XBRL rows with no table row."""
        pe = filing.period_end.isoformat()
        contexts, facts, _text, schedule = self.load_xbrl(filing, self.identifier_parser())
        notes = linked_footnotes(filing.path, contexts, facts, pe)
        h = self.cfg["html"]
        html_rows = parse_main_schedule(filing.path, h["amounts_after_maturity"], h["par_on_rows_without_maturity"])

        index: dict[tuple, list[int]] = defaultdict(list)
        for i, x in enumerate(schedule):
            index[_key(x["principal"], x["cost"], x["fair_value"])].append(i)

        used: set[int] = set()
        pairs: list[tuple[HtmlRow, dict]] = []
        with_amounts = [r for r in html_rows if r.amount_cells > 0]
        self.stats["html_rows"] = len(with_amounts)
        for hr in with_amounts:
            cands = [i for i in index.get(_key(hr.principal, hr.cost, hr.fair_value, 1000), []) if i not in used]
            if not cands:
                self.stats["html_unmatched"] += 1
                continue
            if len(cands) > 1:
                self.stats["html_multi_candidates"] += 1
                same = [i for i in cands if _alnum(schedule[i]["raw_name"]) == _alnum(hr.name)]
                if same:
                    cands = same
                    self.stats["multi_resolved_by_name"] += 1
                else:
                    self.stats["multi_resolved_by_order_unexplained"] += 1
            used.add(cands[0])
            pairs.append((hr, schedule[cands[0]]))
        self.stats["matched"] = len(pairs)
        dropped = [x for i, x in enumerate(schedule) if i not in used]
        self.stats["xbrl_schedule_rows"] = len(schedule)
        self.stats["xbrl_dropped_no_main_schedule_row"] = len(dropped)
        self.stats["xbrl_dropped_funded"] = sum(1 for x in dropped if x["principal"] not in (None, 0))
        self.stats["xbrl_dropped_fair_value_sum"] = int(sum((x["fair_value"] or Decimal(0)) for x in dropped))
        return pairs, dropped, notes

    def parse(self, filing: Filing) -> list[RawRow]:
        pairs, _dropped, notes = self.match(filing)
        out: list[RawRow] = []
        for order, (hr, x) in enumerate(pairs, start=1):
            name = self.pick_name(x, hr)
            if _alnum(name) != _alnum(x["raw_name"]):
                self.stats["name_differs_between_html_and_xbrl"] += 1
            out.append((name, hr.industry, self.pick_instrument(x, hr), self.rate_text(hr), self.maturity_text(hr),
                        plain(x["principal"]), unit_text(x), plain(x["cost"]), plain(x["fair_value"]),
                        " | ".join(notes.get(x["identifier"], [])) or None, order, filing.source_url))
        self.stats["rows"] = len(out)
        return out


class HpsAdapter(HtmlAssistedAdapter):
    """XBRL identifiers read 'Name N | Non-Affiliated Issuer' where N is an XBRL disambiguation index, so
    the printed name (without footnote markers) is used. HPS typing stays by lien class: the section
    header. No row level revolver or delayed draw rule."""

    def pick_name(self, x: dict, html: HtmlRow) -> str:
        return html.name

    def pick_instrument(self, x: dict, html: HtmlRow) -> str | None:
        return html.section

    def rate_text(self, html: HtmlRow) -> str | None:
        toks = [t for t in html.rate_tokens if "%" in t or re.fullmatch(r"[A-Z]{1,4}\s*\+", t)]
        return " ".join(toks) or None   # 'SF + 5.38% (incl 2.88% PIK)'; the all-in rate is not kept


class OrcicAdapter(HtmlAssistedAdapter):
    """ORCIC identifiers carry a clean name and the row level type; the table adds maturity, industry and
    the Ref. Rate / Cash / PIK columns. Maturity is kept as printed, month and year ("8/2029"); normalize
    converts M/YYYY to the month end."""

    def pick_name(self, x: dict, html: HtmlRow) -> str:
        return x["raw_name"]

    def pick_instrument(self, x: dict, html: HtmlRow) -> str | None:
        return x["instrument_type"] or html.instrument_cell

    def rate_text(self, html: HtmlRow) -> str | None:
        t = html.rate_tokens
        if not t:
            return None
        if len(t) >= 3:   # Ref. Rate, Cash, PIK columns
            return f"{t[0]} {t[1]} Cash plus {t[2]} PIK"
        return " ".join(t)


ADAPTERS = {"ads": AdsAdapter, "hps": HpsAdapter, "orcic": OrcicAdapter}


def make_adapter(key: str, cfg: dict) -> FilerAdapter:
    return ADAPTERS[cfg["adapter"]](cfg)
