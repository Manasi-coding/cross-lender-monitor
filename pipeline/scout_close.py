"""Day 1 final close-out analysis. Read-only: fixtures only, no database, no network.

Run: python -m pipeline.scout_close
1. dropped XBRL rows (no main schedule row) for HPS and ORCIC
2. HPS revolver / delayed draw text among funded rows
3. crude cross-BDC candidate pair estimate for ADS, HPS and ORCIC (not matching)
"""
from __future__ import annotations

import calendar
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from itertools import combinations

from pipeline import ixbrl as X
from pipeline.ixbrl import assemble_investments, parse_ixbrl, split_pipe_identifier
from pipeline.scout_html import (AMOUNT_SCALE, PE, RAW, _key, parse_schedule, xbrl_rows, join)

HPS, ORCIC, ADS = "hps_corporate_lending", "blue_owl_credit_income", "ads"
DROP_TOKENS = {"llc", "inc", "corp", "lp", "ltd", "plc", "holdings", "holdco"}
TYPE_WORDS = ("revolv", "delayed", "ddtl")


def unit(r: dict) -> str:
    u = (r["principal_unit"] or "").lower()
    return u[2:] if u.startswith("u_") else u


def base_name(s: str) -> str:
    s = re.sub(r"(\(\d+\))+", " ", s)          # footnote markers
    s = re.sub(r"\s+-\s+[A-Za-z0-9 .,\-]+$", "", s)  # ' - Common Stock' style suffix
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def name_tokens(s: str) -> tuple[str, ...]:
    s = re.sub(r"\(.*?\)", " ", s.lower())
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    return tuple(t for t in s.split() if t not in DROP_TOKENS)


def lien_class(text: str | None) -> str | None:
    t = (text or "").lower()
    if "first lien" in t or "1st lien" in t:
        return "FIRST"
    if "second lien" in t or "2nd lien" in t:
        return "SECOND"
    if any(k in t for k in ("unsecured", "subordinated", "mezzanine")):
        return "UNSECURED"
    return None


def month_end(s: str | None) -> date | None:
    if not s:
        return None
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", s.strip())
    if m:
        return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
    m = re.fullmatch(r"(\d{1,2})/(\d{4})", s.strip())
    if m:
        y, mo = int(m.group(2)), int(m.group(1))
        return date(y, mo, calendar.monthrange(y, mo)[1])
    return None


def load_main(label: str):
    """XBRL schedule rows that also appear in the main HTML schedule, with the HTML row attached."""
    s = parse_schedule(label)
    _, _, xr = xbrl_rows(label)
    j = join(s["rows"], xr)
    sched, idx = j["sched"], j["idx"]
    attached: dict[int, dict] = {}
    for h in s["rows"]:
        if h["cost"] is None and h["fair_value"] is None:
            continue
        hits = idx.get(_key(h["principal"], h["cost"], h["fair_value"], AMOUNT_SCALE), [])
        if len(hits) > 1:
            same = [i for i in hits if base_name(sched[i]["raw_name"]) == base_name(h["name"])]
            hits = same or hits
        for i in hits:
            attached.setdefault(i, h)
    return s, sched, attached


def funded(r: dict) -> bool:
    return r["principal"] not in (None, 0) and r["fair_value"] is not None


def part1() -> None:
    print("\n=== 1. XBRL rows with no main schedule row ===")
    for label in (HPS, ORCIC):
        s, sched, att = load_main(label)
        drop = [r for i, r in enumerate(sched) if i not in att]
        fv = sum((r["fair_value"] or Decimal(0)) for r in drop)
        nz = [r for r in drop if r["principal"] not in (None, 0)]
        print(f"{label}: dropped {len(drop)}, nonzero principal {len(nz)}, "
              f"zero principal {sum(1 for r in drop if r['principal'] == 0)}, "
              f"no principal {sum(1 for r in drop if r['principal'] is None)}, fair value sum {fv:,.0f}")
        print(f"   nonzero-principal fair value sum {sum((r['fair_value'] or Decimal(0)) for r in nz):,.0f}")
        for r in drop[:30]:
            print(f"   {r['raw_name'][:55]:<55} principal={r['principal']} cost={r['cost']} fv={r['fair_value']}")


def part2() -> None:
    print("\n=== 2. HPS funded rows with revolver / delayed draw text ===")
    s, sched, att = load_main(HPS)
    unf = defaultdict(set)
    for u in s["unfunded"]:
        if len(u["raw"]) >= 2:
            unf[base_name(u["raw"][0])].add(u["raw"][1])
    fr = [(i, r) for i, r in enumerate(sched) if funded(r) and i in att]
    print(f"funded rows in the main schedule: {len(fr)}")
    in_name = [(i, r) for i, r in fr if any(w in (att[i]["name"] + " " + r["identifier"]).lower() for w in TYPE_WORDS)]
    print(f"   rows whose name, identifier or HTML cell text contains {TYPE_WORDS}: "
          f"{sum(1 for i, r in fr if any(w in ' '.join(att[i]['raw']).lower() for w in TYPE_WORDS))} (HTML cells), "
          f"{len(in_name)} (name or identifier)")
    neg = [(i, r) for i, r in fr if (r["cost"] is not None and r["cost"] < 0) or r["fair_value"] < 0]
    print(f"   rows with negative cost or negative fair value (unfunded style): {len(neg)}")
    hit = []
    for i, r in fr:
        types = unf.get(base_name(r["raw_name"]), set())
        kinds = {w for t in types for w in TYPE_WORDS if w in t.lower()}
        if kinds:
            hit.append((i, r, types))
    print(f"   rows whose borrower is in the unfunded commitments table with revolving or delayed draw type: {len(hit)}")
    by_sec = Counter(att[i]["section"] for i, _, _ in hit)
    print("   by section header:", dict(by_sec))
    hit_neg = sum(1 for i, r, _ in hit if (r["cost"] is not None and r["cost"] < 0) or r["fair_value"] < 0)
    print(f"   of those, with negative cost or fair value: {hit_neg}")
    kinds_c = Counter()
    for _, _, types in hit:
        for t in types:
            kinds_c[t] += 1
    print("   commitment types seen:", dict(kinds_c.most_common(8)))
    print("   10 samples:")
    for i, r, types in hit[:10]:
        print(f"      {att[i]['name'][:48]:<48} section={att[i]['section']!r} par={r['principal']} cost={r['cost']} "
              f"fv={r['fair_value']} unfunded types={sorted(types)}")


def collect(label: str) -> list[dict]:
    """USD principal, nonzero principal, with fair value. HPS and ORCIC restricted to the main schedule."""
    out = []
    if label == ADS:
        c, f, t = parse_ixbrl(RAW / f"{ADS}_10q_{PE}.htm")
        rows = assemble_investments(c, f, t, PE, identifier_parser=X._split_identifier)
        for r in rows:
            if funded(r) and unit(r) == "usd":
                out.append({"name": r["raw_name"], "tok": name_tokens(r["raw_name"]), "lien": lien_class(r["instrument_type"]),
                            "mat": month_end(r["maturity"].replace("-", "/")) if False else (date.fromisoformat(r["maturity"]) if r["maturity"] else None),
                            "spread": r["spread_bps"], "neg": (r["cost"] or 0) < 0 or r["fair_value"] < 0, "fn6": False})
        return out
    s, sched, att = load_main(label)
    for i, r in enumerate(sched):
        if not (funded(r) and unit(r) == "usd" and i in att):
            continue
        h = att[i]
        lien = lien_class(r["instrument_type"]) or lien_class(h.get("instrument_type_row")) or \
            lien_class(h.get("section"))
        out.append({"name": r["raw_name"], "tok": name_tokens(r["raw_name"]), "lien": lien,
                    "mat": month_end(h["maturity"]), "spread": r["spread_bps"],
                    "neg": (r["cost"] or 0) < 0 or r["fair_value"] < 0,
                    "fn6": "(6)" in h["name"]})
    return out


def names_equal(a: dict, b: dict, a_is_ads: bool, b_is_ads: bool) -> bool:
    ta, tb = a["tok"], b["tok"]
    if len(ta) == 0 or len(tb) == 0:
        return False
    if a_is_ads == b_is_ads:
        return ta == tb
    ads_t, oth = (ta, tb) if a_is_ads else (tb, ta)
    return len("".join(oth)) >= 6 and len(ads_t) >= len(oth) and ads_t[len(ads_t) - len(oth):] == oth


def part3() -> None:
    print("\n=== 3. Crude cross-BDC candidate pair estimate (not matching) ===")
    data = {l: collect(l) for l in (ADS, HPS, ORCIC)}
    for l, rows in data.items():
        print(f"{l}: usd nonzero funded rows {len(rows)}, with lien class {sum(1 for r in rows if r['lien'])}, "
              f"with maturity {sum(1 for r in rows if r['mat'])}, with spread {sum(1 for r in rows if r['spread'] is not None)}")
    for variant, keep in (("all usd funded rows", lambda r: True), ("excluding negative cost or fair value rows", lambda r: not r["neg"])):
        print(f"\n-- {variant}")
        tot = Counter(); names_all = set(); names_pair = defaultdict(set)
        for a, b in combinations((ADS, HPS, ORCIC), 2):
            c = Counter()
            ns = set()
            B = [r for r in data[b] if keep(r)]
            for ra in (r for r in data[a] if keep(r)):
                for rb in B:
                    if not names_equal(ra, rb, a == ADS, b == ADS):
                        continue
                    c["name"] += 1
                    if ra["lien"] and rb["lien"] and ra["lien"] != rb["lien"]:
                        continue
                    c["name+type"] += 1
                    if ra["mat"] and rb["mat"] and abs((ra["mat"] - rb["mat"]).days) > 92:
                        continue
                    c["name+type+maturity"] += 1
                    if ra["spread"] is not None and rb["spread"] is not None and abs(ra["spread"] - rb["spread"]) > 50:
                        continue
                    c["all gates"] += 1
                    ns.add(rb["tok"] if b != ADS else ra["tok"])
            print(f"   {a} - {b}: " + ", ".join(f"{k} {c[k]}" for k in ("name", "name+type", "name+type+maturity", "all gates"))
                  + f" | distinct names {len(ns)}")
            tot.update(c)
            names_all |= {(a, b, n) for n in ns}
        print(f"   total pairs after all gates {tot['all gates']} (name only {tot['name']}); "
              f"distinct (BDC pair, name) combinations {len(names_all)}")
        # distinct names across all three pairs, keyed by the non-ADS token tuple where possible
        print("   distinct borrower names across all pairs:", len({n for _, _, n in names_all}))


def main() -> None:
    which = sys.argv[1:] or ["1", "2", "3"]
    if "1" in which:
        part1()
    if "2" in which:
        part2()
    if "3" in which:
        part3()


if __name__ == "__main__":
    main()
