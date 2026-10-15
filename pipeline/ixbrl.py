"""Generic Inline XBRL reader. Makes no assumptions about tag names.

parse_ixbrl(path) returns contexts (id -> period and dimension members) and
numeric facts (ix:nonFraction) with their context resolved.
"""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from lxml import etree

NS_IX = "http://www.xbrl.org/2013/inlineXBRL"
NS_XBRLI = "http://www.xbrl.org/2003/instance"
NS_XBRLDI = "http://xbrl.org/2006/xbrldi"


@dataclass
class Context:
    id: str
    start: str | None
    end: str | None
    instant: str | None
    # axis -> member. Explicit members are QNames, typed members are their text value.
    explicit: dict[str, str] = field(default_factory=dict)
    typed: dict[str, str] = field(default_factory=dict)

    @property
    def dims(self) -> dict[str, str]:
        return {**self.explicit, **self.typed}


@dataclass
class Fact:
    name: str
    context_ref: str
    unit: str | None
    value: Decimal | None
    raw: str
    decimals: str | None
    is_nil: bool


def _text(el) -> str | None:
    return el.text.strip() if el is not None and el.text else None


def _parse_contexts(root) -> dict[str, Context]:
    out: dict[str, Context] = {}
    for c in root.iter(f"{{{NS_XBRLI}}}context"):
        period = c.find(f"{{{NS_XBRLI}}}period")
        ctx = Context(
            id=c.get("id"),
            start=_text(period.find(f"{{{NS_XBRLI}}}startDate")),
            end=_text(period.find(f"{{{NS_XBRLI}}}endDate")),
            instant=_text(period.find(f"{{{NS_XBRLI}}}instant")),
        )
        for m in c.iter(f"{{{NS_XBRLDI}}}explicitMember"):
            ctx.explicit[m.get("dimension")] = (m.text or "").strip()
        for m in c.iter(f"{{{NS_XBRLDI}}}typedMember"):
            child = next(iter(m), None)
            val = "".join(child.itertext()).strip() if child is not None else ""
            ctx.typed[m.get("dimension")] = val
        out[ctx.id] = ctx
    return out


def _fact_value(el) -> tuple[Decimal | None, str, bool]:
    raw = "".join(el.itertext()).strip()
    if el.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
        return None, raw, True
    cleaned = raw.replace(",", "")
    if cleaned in ("", "-", "—", "–"):
        # ix:nonFraction with a dash format means zero
        return (Decimal(0) if raw else None), raw, False
    try:
        v = Decimal(cleaned)
    except InvalidOperation:
        return None, raw, False
    scale = int(el.get("scale") or 0)
    v = v.scaleb(scale)
    if el.get("sign") == "-":
        v = -v
    return v, raw, False


def parse_ixbrl(path: Path) -> tuple[dict[str, Context], list[Fact], list[tuple[str, str, str]]]:
    tree = etree.parse(str(path), etree.XMLParser(huge_tree=True, recover=True))
    root = tree.getroot()
    contexts = _parse_contexts(root)
    facts: list[Fact] = []
    for el in root.iter(f"{{{NS_IX}}}nonFraction"):
        value, raw, nil = _fact_value(el)
        facts.append(Fact(
            name=el.get("name"),
            context_ref=el.get("contextRef"),
            unit=el.get("unitRef"),
            value=value,
            raw=raw,
            decimals=el.get("decimals"),
            is_nil=nil,
        ))
    text_facts = [
        (el.get("name"), el.get("contextRef"), " ".join("".join(el.itertext()).split()))
        for el in root.iter(f"{{{NS_IX}}}nonNumeric")
    ]
    return contexts, facts, text_facts


# ---------------------------------------------------------------------------
# Assembly of investments. Tag and axis names below were verified on the ADS
# 10-Q for 2026-06-30 (see docs/day1_notes.md), not assumed. Other filers must
# be re-verified, so the names are parameters, not hidden constants.
# ---------------------------------------------------------------------------
IDENTIFIER_AXIS = "us-gaap:InvestmentIdentifierAxis"
INVESTMENT_TAGS = {
    "fair_value": "us-gaap:InvestmentOwnedAtFairValue",
    "principal": "us-gaap:InvestmentOwnedBalancePrincipalAmount",
    "cost": "us-gaap:InvestmentOwnedAtCost",
    "spread": "us-gaap:InvestmentBasisSpreadVariableRate",
    "floor": "us-gaap:InvestmentInterestRateFloor",
    "fixed_rate": "us-gaap:InvestmentInterestRate",
    "pik_rate": "us-gaap:InvestmentInterestRatePaidInKind",
    "shares": "us-gaap:InvestmentOwnedBalanceShares",
}
TEXT_TAGS = {
    "maturity": "us-gaap:InvestmentMaturityDate",
    "reference_rate": "us-gaap:InvestmentVariableInterestRateTypeExtensibleEnumeration",
}


def _split_identifier(ident: str) -> tuple[str, str | None]:
    """Split the typed identifier into (raw name text, instrument type).

    The identifier reads '<industry> <company> <legal name> Investment Type
    <instrument> Interest Rate <rate> Maturity Date <date>'. The industry,
    company and legal name run together, so the raw name keeps all three.
    """
    m = re.split(r"\s+Investment Type\s+", ident, maxsplit=1)
    name = m[0].strip()
    if len(m) < 2:
        return name, None
    inst = re.split(r"\s+(?:Interest Rate|Maturity Date)\b", m[1], maxsplit=1)[0].strip()
    return name, inst or None


AFFILIATION_WORDS = ("affiliated", "controlled", "non-controlled")


def split_pipe_identifier(ident: str) -> tuple[str, str | None]:
    """Identifier format 'Name [N] | [instrument |] affiliation' used by ARCC, OBDC,
    ORCIC, BXSL and HPS. A trailing duplicate index (' 1', ' 2') is dropped."""
    parts = [p.strip() for p in ident.split("|")]
    name = re.sub(r"\s+\d+$", "", parts[0]).strip()
    inst = None
    if len(parts) > 1 and not any(w in parts[1].lower() for w in AFFILIATION_WORDS):
        inst = parts[1] or None
    return name, inst


def _iso_date(s: str | None) -> str | None:
    if not s:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s.strip(), fmt).date().isoformat()
        except ValueError:
            pass
    return None


def assemble_investments(contexts: dict[str, Context], facts: list[Fact],
                         text_facts: list[tuple[str, str, str]], period_end: str,
                         tags: dict[str, str] = INVESTMENT_TAGS,
                         text_tags: dict[str, str] = TEXT_TAGS,
                         identifier_parser=_split_identifier) -> list[dict]:
    """Group facts that share the same dimension members (the typed investment
    identifier) at the measured instant into one record per investment."""
    by_tag = {v: k for k, v in tags.items()}
    by_text = {v: k for k, v in text_tags.items()}
    rows: dict[str, dict] = defaultdict(dict)
    for f in facts:
        key = by_tag.get(f.name)
        c = contexts.get(f.context_ref)
        if key is None or c is None or c.instant != period_end or IDENTIFIER_AXIS not in c.typed:
            continue
        if len(c.dims) != 1:
            continue  # only rows identified by the investment identifier alone
        rows[c.typed[IDENTIFIER_AXIS]].setdefault(key, f.value)
        rows[c.typed[IDENTIFIER_AXIS]].setdefault(key + "_unit", f.unit)
    for name, ref, text in text_facts:
        key = by_text.get(name)
        c = contexts.get(ref)
        if key is None or c is None or c.instant != period_end or IDENTIFIER_AXIS not in c.typed:
            continue
        rows[c.typed[IDENTIFIER_AXIS]].setdefault(key, text)
    out = []
    for ident, r in rows.items():
        raw_name, inst = identifier_parser(ident)
        ref = r.get("reference_rate")
        spread = r.get("spread")
        out.append({
            "identifier": ident,
            "raw_name": raw_name,
            "instrument_type": inst,
            "principal": r.get("principal"),
            "principal_unit": r.get("principal_unit"),
            "cost": r.get("cost"),
            "fair_value": r.get("fair_value"),
            "maturity": _iso_date(r.get("maturity")),
            "reference_rate": ref.rsplit("#", 1)[-1] if ref else None,
            "spread_bps": spread * 10000 if spread is not None else None,
            "floor_pct": r.get("floor") * 100 if r.get("floor") is not None else None,
            "fixed_rate": r.get("fixed_rate"),
            "pik_rate": r.get("pik_rate"),
            "shares": r.get("shares"),
        })
    return out


def summarize_parse(rows: list[dict], threshold: float = 0.90) -> dict:
    """Parse quality of assembled investment rows, as two rates.

    Definitions:
    - schedule row: a row with a fair value or a cost. Rows with neither are
      identifier fragments, not schedule lines.
    - funded row: a schedule row whose principal is not None and not zero.
      Unfunded commitments, equity and zero-principal delayed draw or revolver
      lines are not funded rows.
    - parsed row: a funded row that also has a fair value.

    all_rows_pct    = parsed rows / schedule rows. For information only.
    funded_rows_pct = parsed rows / funded rows.
    The recommendation uses the funded-row rate only (Day 1 decision for ADS:
    the all-rows rate is pulled down by unfunded commitments and equity).
    "pct" is kept as an alias of all_rows_pct for the scout scripts.
    """
    schedule = [r for r in rows if r["fair_value"] is not None or r["cost"] is not None]
    funded = [r for r in schedule if r["principal"] is not None and r["principal"] != 0]
    parsed = [r for r in funded if r["fair_value"] is not None]
    all_pct = len(parsed) / len(schedule) if schedule else 0.0
    funded_pct = len(parsed) / len(funded) if funded else 0.0
    return {
        "schedule_rows": len(schedule),
        "rows_with_principal_and_fair_value": len(parsed),
        "all_rows_pct": all_pct,
        "pct": all_pct,
        "funded_rows": len(funded),
        "funded_rows_with_fair_value": len(parsed),
        "funded_rows_pct": funded_pct,
        "recommendation": "xbrl_first" if funded_pct >= threshold else "html_tables_pandas",
    }
