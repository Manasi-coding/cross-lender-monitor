"""Day 1 read-only: which funded rows carry an "unfunded" footnote, by filer.

Method: inline XBRL footnotes (ix:footnote) are linked by ix:relationship to the
principal, cost and fair value facts of each investment identifier at the measured
period end. A funded row (nonzero principal and fair value present) is counted when
a linked footnote text matches the pattern. Detection is by text, never by footnote
number. Fixtures only: no database, no network.

Run: python -m pipeline.scout_footnotes

Two views are printed per filer:
- generic: any footnote containing "unfunded" (what a naive rule would flag)
- configured: the per-filer pattern below (HPS: "unfunded loan commitment"; ORCIC and
  ADS: no pattern, because the evidence shows no basis problem)
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from lxml import etree

from pipeline import ixbrl as X
from pipeline.ixbrl import (IDENTIFIER_AXIS, NS_IX, assemble_investments, parse_ixbrl,
                            split_pipe_identifier)

RAW = Path(__file__).resolve().parent.parent / "fixtures" / "raw"
PE = "2026-06-30"

# Per-filer configured footnote pattern. None means the filer has no pattern.
FILERS = {
    "ads": ("Apollo Debt Solutions (ADS)", None),
    "hps_corporate_lending": ("HPS Corporate Lending", "unfunded loan commitment"),
    "blue_owl_credit_income": ("Blue Owl Credit Income (ORCIC)", None),
}
GENERIC = "unfunded"


def _unit(r: dict) -> str:
    u = (r["principal_unit"] or "").lower()
    return u[2:] if u.startswith("u_") else u


def analyse(label: str) -> dict:
    path = RAW / f"{label}_10q_{PE}.htm"
    root = etree.parse(str(path), etree.XMLParser(huge_tree=True, recover=True)).getroot()
    notes = {el.get("id"): " ".join("".join(el.itertext()).split())
             for el in root.iter(f"{{{NS_IX}}}footnote")}
    fact_notes: dict[str, set[str]] = defaultdict(set)
    for rel in root.iter(f"{{{NS_IX}}}relationship"):
        for a in (rel.get("fromRefs") or "").split():
            fact_notes[a].update((rel.get("toRefs") or "").split())

    contexts, facts, text_facts = parse_ixbrl(path)
    elements = list(root.iter(f"{{{NS_IX}}}nonFraction"))
    assert len(elements) == len(facts)  # parse_ixbrl keeps document order
    ident_notes: dict[str, set[str]] = defaultdict(set)
    for el, fact in zip(elements, facts):
        fid = el.get("id")
        if not fid or fid not in fact_notes:
            continue
        c = contexts.get(fact.context_ref)
        if c and c.instant == PE and IDENTIFIER_AXIS in c.typed and len(c.dims) == 1:
            ident_notes[c.typed[IDENTIFIER_AXIS]].update(fact_notes[fid])

    parser = X._split_identifier if label == "ads" else split_pipe_identifier
    rows = assemble_investments(contexts, facts, text_facts, PE, identifier_parser=parser)
    funded = [r for r in rows if r["principal"] not in (None, 0) and r["fair_value"] is not None]

    def flagged(pattern: str | None) -> list[dict]:
        if not pattern:
            return []
        ids = {i for i, t in notes.items() if pattern.lower() in t.lower()}
        return [r for r in funded if ident_notes.get(r["identifier"], set()) & ids]

    def split(sel: list[dict]) -> dict:
        neg = [r for r in sel if (r["cost"] or 0) < 0 or r["fair_value"] < 0]
        return {"rows": len(sel), "negative": len(neg), "positive": len(sel) - len(neg),
                "usd": sum(1 for r in sel if _unit(r) == "usd")}

    return {"funded": len(funded), "footnotes": len(notes),
            "generic": split(flagged(GENERIC)),
            "configured": split(flagged(FILERS[label][1]))}


def main() -> None:
    print(f"Funded rows = nonzero principal and fair value, period end {PE}\n")
    for label, (title, pattern) in FILERS.items():
        a = analyse(label)
        print(f"{title}: funded rows {a['funded']}, footnotes {a['footnotes']}")
        g, c = a["generic"], a["configured"]
        print(f"   generic match '{GENERIC}': {g['rows']} rows "
              f"({g['negative']} negative, {g['positive']} positive, {g['usd']} with USD principal)")
        shown = f"'{pattern}'" if pattern else "none"
        print(f"   configured pattern {shown}: {c['rows']} rows "
              f"({c['negative']} negative, {c['positive']} positive, {c['usd']} with USD principal)")


if __name__ == "__main__":
    main()
