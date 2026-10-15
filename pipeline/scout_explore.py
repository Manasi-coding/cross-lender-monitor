"""Day 1 read-only exploration: where do maturity and instrument type live?
Run: python -m pipeline.scout_explore
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path

from lxml import etree

from pipeline.ixbrl import NS_IX, parse_ixbrl

RAW = Path(__file__).resolve().parent.parent / "fixtures" / "raw"
IDAX = "us-gaap:InvestmentIdentifierAxis"


def main() -> None:
    for label in ("hps_corporate_lending", "blue_owl_credit_income"):
        p = RAW / f"{label}_10q_2026-06-30.htm"
        ctxs, facts, texts = parse_ixbrl(p)
        print(f"\n=== {label}")
        # all nonNumeric fact names and how many sit on identifier contexts
        c_all, c_id = Counter(), Counter()
        for n, r, _ in texts:
            c_all[n] += 1
            if r in ctxs and IDAX in ctxs[r].typed:
                c_id[n] += 1
        print("nonNumeric on identifier contexts:", dict(c_id))
        print("nonNumeric names with Maturity/Type/Date/Rate:",
              {k: v for k, v in c_all.items() if any(w in k for w in ("Maturity", "Type", "Date", "Rate"))})
        # nonFraction names on identifier contexts
        nf = Counter(f.name for f in facts if f.context_ref in ctxs and IDAX in ctxs[f.context_ref].typed)
        print("nonFraction names on identifier contexts:", nf.most_common(15))
        # raw html: any ix tag other than nonFraction/nonNumeric in the schedule?
        tree = etree.parse(str(p), etree.XMLParser(huge_tree=True, recover=True))
        root = tree.getroot()
        tags = Counter(etree.QName(e).localname for e in root.iter() if isinstance(e.tag, str) and e.tag.startswith("{" + NS_IX))
        print("ix element kinds:", dict(tags))
        # HTML schedule table header sample
        hits = 0
        for tr in root.iter("{http://www.w3.org/1999/xhtml}tr", "tr"):
            t = " ".join("".join(tr.itertext()).split())
            if "Maturity" in t and ("Spread" in t or "Reference" in t) and hits < 2:
                print("HTML header row:", t[:300])
                hits += 1
        # sample of identifiers
        ids = [c.typed[IDAX] for c in ctxs.values() if IDAX in c.typed][:3]
        print("sample identifiers:", ids)


COMMIT = "us-gaap:InvestmentCompanyFinancialCommitmentToInvesteeFutureAmount"
PE = "2026-06-30"


def analyze() -> None:
    from itertools import combinations
    from pipeline.ixbrl import assemble_investments, split_pipe_identifier, INVESTMENT_TAGS
    from pipeline.scout import norm_tokens, _unit
    data, parsed_ctx = {}, {}
    for label in ("ads", "hps_corporate_lending", "blue_owl_credit_income"):
        ctxs, facts, texts = parse_ixbrl(RAW / f"{label}_10q_{PE}.htm")
        kw = {} if label == "ads" else {"identifier_parser": split_pipe_identifier}
        data[label] = assemble_investments(ctxs, facts, texts, PE, **kw)
        parsed_ctx[label] = (ctxs, facts)
    # borrower sets: token tuple -> usd flag. ADS has an industry prefix, others do not.
    sets = {}
    for label, rows in data.items():
        d = {}
        for r in rows:
            if r["principal"] is None or r["fair_value"] is None:
                continue
            t = norm_tokens(r["raw_name"])
            if len("".join(t)) < 6:
                continue
            d[t] = d.get(t, False) or _unit(r) == "usd"
        sets[label] = d

    def key(a, b):
        # canonical key: the shorter name (the one without industry prefix) if it is a token suffix of the other
        return b if len(a) >= len(b) and a[len(a) - len(b):] == b else None

    ads = sets["ads"]

    def to_ads(d):
        out = {}
        for t, usd in d.items():
            for a in ads:
                if key(a, t):
                    out[a] = (out.get(a, False) or usd) and ads[a]
                    out.setdefault(a, usd and ads[a])
                    out[a] = out[a] or (usd and ads[a])
        return out
    # everything expressed in ADS's token form (ADS is the only prefixed one)
    m = {"ads": dict(ads), "hps": to_ads(sets["hps_corporate_lending"]), "orcic": to_ads(sets["blue_owl_credit_income"])}
    print("\n--- borrower overlap (ADS-token space; HPS and ORCIC matched to ADS first)")
    # HPS-ORCIC direct (neither prefixed): exact token equality
    h, o = sets["hps_corporate_lending"], sets["blue_owl_credit_income"]
    ho_all = set(h) & set(o)
    ho_usd = {t for t in ho_all if h[t] and o[t]}
    ha, oa = m["hps"], m["orcic"]
    print(f"ADS-HPS   all={len(ha)} usd={sum(ha.values())}")
    print(f"ADS-ORCIC all={len(oa)} usd={sum(oa.values())}")
    print(f"HPS-ORCIC all={len(ho_all)} usd={len(ho_usd)}")
    tri_all = {t for t in ho_all if any(key(a, t) for a in ha) and any(key(a, t) for a in oa)}
    tri_usd = {t for t in tri_all if t in ho_usd and any(key(a, t) and ha[a] and oa.get(a) for a in ha)}
    print(f"All three all={len(tri_all)} usd={len(tri_usd)}")
    print("sample triple:", [" ".join(t) for t in list(tri_all)[:5]])

    for label in ("hps_corporate_lending", "blue_owl_credit_income"):
        rows = [r for r in data[label] if r["principal"] is not None and r["fair_value"] is not None]
        print(f"\n--- {label} sample parsed rows")
        for r in rows[:5]:
            print(f"  {r['raw_name'][:40]!r} type={r['instrument_type']!r} mat={r['maturity']} "
                  f"spread_bps={r['spread_bps']} prin={r['principal']} {r['principal_unit']} cost={r['cost']} fv={r['fair_value']}")

        ctxs, facts = parsed_ctx[label]
        by = {}
        for f in facts:
            c = ctxs.get(f.context_ref)
            if c is None or c.instant != PE or IDAX not in c.typed or len(c.dims) != 1:
                continue
            by.setdefault(c.typed[IDAX], {}).setdefault(f.name, f.value)
        sched = {i: t for i, t in by.items()
                 if INVESTMENT_TAGS["fair_value"] in t or INVESTMENT_TAGS["cost"] in t}
        unparsed = {i: t for i, t in sched.items()
                    if INVESTMENT_TAGS["principal"] not in t or INVESTMENT_TAGS["fair_value"] not in t}
        eq = [i for i, t in unparsed.items() if INVESTMENT_TAGS["shares"] in t]
        eq_name = [i for i, t in unparsed.items() if i not in eq and any(
            w in i.lower() for w in ("equity", "preferred", "common", "warrant", "units", "membership", "partnership interest"))]
        unf = [i for i, t in unparsed.items() if i not in eq and i not in eq_name and COMMIT in t]
        other = [i for i in unparsed if i not in eq and i not in eq_name and i not in unf]
        nofv = [i for i in unparsed if INVESTMENT_TAGS["fair_value"] not in unparsed[i]]
        print(f"schedule rows={len(sched)} unparsed={len(unparsed)}: equity(shares tag)={len(eq)} "
              f"equity(by name)={len(eq_name)} unfunded(commitment tag)={len(unf)} other={len(other)} no_fv={len(nofv)}")
        print("  other samples:", [(i[:60], sorted(k.split(':')[1] for k in unparsed[i])) for i in other[:4]])
        # reconciliation
        fv_sum = sum(t[INVESTMENT_TAGS["fair_value"]] for t in sched.values() if INVESTMENT_TAGS["fair_value"] in t)
        print(f"  sum FV over schedule rows = {fv_sum:,.0f}")
        for f in facts:
            c = ctxs.get(f.context_ref)
            if c and c.instant == PE and not c.dims and f.name in (
                    "us-gaap:InvestmentOwnedAtFairValue", "us-gaap:InvestmentsFairValueDisclosure",
                    "us-gaap:Investments", "us-gaap:InvestmentOwnedAtCost") and f.value is not None:
                print(f"  filing total {f.name} = {f.value:,.0f}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "analyze":
        analyze()
    else:
        main()
