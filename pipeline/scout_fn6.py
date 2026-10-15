"""Day 1 read-only: evidence on HPS footnote (6) rows. Fixtures only.

Run: python -m pipeline.scout_fn6
"""
from __future__ import annotations

from itertools import combinations

import numpy as np

from pipeline import ixbrl as X
from pipeline.ixbrl import assemble_investments, parse_ixbrl
from pipeline.scout import norm_tokens
from pipeline.scout_close import (ADS, HPS, ORCIC, collect, funded, load_main, names_equal, unit)
from pipeline.scout_html import PE, RAW

FN6_TEXT = ("Position or portion thereof is an unfunded loan commitment, and no interest is being earned on the "
            "unfunded portion, although the investment may be subject to unused commitment fees. Negative cost "
            "and fair value results from unamortized fees, which are capitalized to the investment cost.")


def pct(vals):
    a = np.array([float(v) for v in vals])
    return len(a), np.percentile(a, 10), np.median(a), np.percentile(a, 90)


def hps_rows():
    s, sched, att = load_main(HPS)
    out = []
    for i, r in enumerate(sched):
        if funded(r) and i in att and att[i]["maturity"] is not None:
            neg = (r["cost"] or 0) < 0 or r["fair_value"] < 0
            out.append({"r": r, "h": att[i], "fn6": "(6)" in att[i]["name"], "neg": neg, "usd": unit(r) == "usd"})
    return out


def ads_all():
    c, f, t = parse_ixbrl(RAW / f"{ADS}_10q_{PE}.htm")
    rows = assemble_investments(c, f, t, PE, identifier_parser=X._split_identifier)
    return [r for r in rows if funded(r)]


def main_rows(label):
    s, sched, att = load_main(label)
    return [r for i, r in enumerate(sched) if funded(r) and i in att and att[i]["maturity"] is not None]


def part_a() -> None:
    H = hps_rows()
    print(f"HPS main schedule debt rows with principal: {len(H)} (usd principal {sum(1 for x in H if x['usd'])})")
    print(f"   footnote (6): {sum(x['fn6'] for x in H)}; negative: {sum(x['neg'] for x in H)}; "
          f"(6) and positive: {sum(1 for x in H if x['fn6'] and not x['neg'])}; "
          f"(6) positive and USD: {sum(1 for x in H if x['fn6'] and not x['neg'] and x['usd'])}")
    groups = {
        "HPS (6) positive": [x["r"] for x in H if x["fn6"] and not x["neg"]],
        "HPS (6) negative": [x["r"] for x in H if x["fn6"] and x["neg"]],
        "HPS no (6)": [x["r"] for x in H if not x["fn6"]],
        "ADS": ads_all(),
        "ORCIC": main_rows(ORCIC),
    }
    print("\nUSD principal rows only. Ratios are plain fractions (1.000 means par).")
    print(f"{'group':<22}{'n':>5}  {'FV/par p10':>10}{'median':>8}{'p90':>8}  {'cost/par p10':>12}{'median':>8}{'p90':>8}")
    for name, rows in groups.items():
        rows = [r for r in rows if unit(r) == "usd" and r["principal"]]
        n, a, b, c = pct([r["fair_value"] / r["principal"] for r in rows])
        _, d, e, f = pct([r["cost"] / r["principal"] for r in rows if r["cost"] is not None])
        print(f"{name:<22}{n:>5}  {a:>10.3f}{b:>8.3f}{c:>8.3f}  {d:>12.3f}{e:>8.3f}{f:>8.3f}")
    pos = [x for x in H if x["fn6"] and not x["neg"]]
    print("\n5 of the 98 positive footnote (6) rows (every 20th, amounts in thousands):")
    for x in pos[::20][:5]:
        print(f"   {x['h']['name'][:60]} | principal {x['h']['principal']} | cost {x['h']['cost']} | "
              f"fv {x['h']['fair_value']} | principal unit {unit(x['r'])}")
    print("   footnote (6) text:", FN6_TEXT)


def toks(rows):
    out = {}
    for r in rows:
        t = norm_tokens(r["raw_name"])
        if len("".join(t)) < 6:
            continue
        out[t] = out.get(t, False) or unit(r) == "usd"
    return out


def part_d() -> None:
    H = hps_rows()
    O = main_rows(ORCIC)
    variants = {
        "baseline (all HPS main rows)": lambda x: True,
        "exclude all (6) rows": lambda x: not x["fn6"],
        "exclude only negative rows": lambda x: not x["neg"],
    }
    ads = toks(ads_all())

    def amatch(t):
        for a in ads:
            if len(a) >= len(t) and a[len(a) - len(t):] == t:
                return a
        return None

    print("\nOverlap gate (distinct names in 2 or more of ADS, HPS, ORCIC; nonzero principal funded rows):")
    TO = toks(O)
    for vname, keep in variants.items():
        TH = toks([x["r"] for x in H if keep(x)])
        mh = {t for t in TH if amatch(t)}
        mo = {t for t in TO if amatch(t)}
        com = {t for t in TH if t in TO}
        union = mh | mo | com
        usd = {t for t in union if TH.get(t, True) and TO.get(t, True) and (not amatch(t) or ads[amatch(t)])}
        three = mh & mo & com
        three_usd = {t for t in three if TH[t] and TO[t] and ads[amatch(t)]}
        print(f"   {vname:<30} in 2 or more: {len(union)} (usd {len(usd)}); in all three: {len(three)} "
              f"(usd {len(three_usd)}); HPS names {len(TH)}")

    print("\nCrude cross-BDC candidate pairs (name, lien class, maturity 92 days, spread 50 bps; USD, nonzero principal):")
    data = {l: collect(l) for l in (ADS, HPS, ORCIC)}
    for vname, keep in (("baseline", lambda r: True), ("exclude all (6) rows", lambda r: not r["fn6"]),
                        ("exclude only negative rows", lambda r: not r["neg"])):
        tot = 0
        names = set()
        per = {}
        for a, b in combinations((ADS, HPS, ORCIC), 2):
            cnt = 0
            for ra in (r for r in data[a] if keep(r)):
                for rb in (r for r in data[b] if keep(r)):
                    if not names_equal(ra, rb, a == ADS, b == ADS):
                        continue
                    if ra["lien"] and rb["lien"] and ra["lien"] != rb["lien"]:
                        continue
                    if ra["mat"] and rb["mat"] and abs((ra["mat"] - rb["mat"]).days) > 92:
                        continue
                    if ra["spread"] is not None and rb["spread"] is not None and abs(ra["spread"] - rb["spread"]) > 50:
                        continue
                    cnt += 1
                    names.add(rb["tok"] if b != ADS else ra["tok"])
            per[(a, b)] = cnt
            tot += cnt
        rows_h = sum(1 for r in data[HPS] if keep(r))
        print(f"   {vname:<28} HPS usd rows {rows_h}; pairs {tot} (ADS-HPS {per[(ADS, HPS)]}, "
              f"ADS-ORCIC {per[(ADS, ORCIC)]}, HPS-ORCIC {per[(HPS, ORCIC)]}); distinct names {len(names)}")


if __name__ == "__main__":
    part_a()
    part_d()
