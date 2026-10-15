"""Day 1 scouting of other BDCs. Read-only: no database writes, no config writes.

Stage 'lookup': confirm CIK/name via submissions API, list latest 10-Q/10-K.
Run: python -m pipeline.scout lookup
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from pipeline.ingest import SecClient

ADS_PERIOD_END = "2026-06-30"

# (label, CIK, expected name fragment). Names are checked, not trusted.
CANDIDATES = [
    ("ares_capital", "0001287750", "ares capital"),
    ("blue_owl_capital_corp", "0001655888", "blue owl capital corporation"),
    ("blackstone_secured_lending", "0001736035", "blackstone secured lending"),
    ("fs_kkr", "0001422183", "fs kkr capital"),
    ("golub_capital_bdc", "0001476765", "golub capital bdc"),
    ("blue_owl_credit_income", "0001812554", "blue owl credit income"),
    ("hps_corporate_lending", "0001838126", "hps corporate lending"),
]


def load_env() -> None:
    env = Path(__file__).resolve().parent.parent / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def latest_periodic(subs: dict, n: int = 3) -> list[dict]:
    r = subs["filings"]["recent"]
    rows = [
        {"form": r["form"][i], "accession": r["accessionNumber"][i], "period_end": r["reportDate"][i],
         "filing_date": r["filingDate"][i], "primary": r["primaryDocument"][i]}
        for i in range(len(r["form"])) if r["form"][i] in ("10-Q", "10-K")
    ]
    rows.sort(key=lambda x: x["filing_date"], reverse=True)
    return rows[:n]


def lookup(client: SecClient) -> None:
    for label, cik, frag in CANDIDATES:
        try:
            subs = client.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json")
        except Exception as e:  # report and continue
            print(f"{label} {cik}: ERROR {e}")
            continue
        name = subs.get("name", "")
        print(f"\n{label} CIK {cik} name={name!r} match={frag in name.lower()}")
        for row in latest_periodic(subs):
            print(f"   {row['form']} {row['accession']} period {row['period_end']} filed {row['filing_date']} {row['primary']}")


SHORTLIST = ["ares_capital", "blue_owl_capital_corp", "blackstone_secured_lending",
             "blue_owl_credit_income", "hps_corporate_lending"]


def latest_for_period(client: SecClient, cik: str, period_end: str) -> dict:
    subs = client.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json")
    for row in latest_periodic(subs, 10):
        if row["period_end"] == period_end:
            return row
    raise RuntimeError(f"no filing for {cik} at {period_end}")


def download(client: SecClient) -> None:
    from pipeline.ingest import download_filing
    for label, cik, _ in CANDIDATES:
        if label not in SHORTLIST:
            continue
        row = latest_for_period(client, cik, ADS_PERIOD_END)
        dest = Path(__file__).resolve().parent.parent / "fixtures" / "raw" / f"{label}_10q_{ADS_PERIOD_END}.htm"
        if dest.exists():
            print(label, "already downloaded", dest.stat().st_size)
            continue
        path, url = download_filing(client, cik, row["accession"], label, ADS_PERIOD_END)
        print(label, row["accession"], url, path.stat().st_size)


def discover() -> None:
    """Per filer: investment-like tags and dimension axes. Nothing assumed."""
    from collections import Counter
    from pipeline.ixbrl import parse_ixbrl
    raw = Path(__file__).resolve().parent.parent / "fixtures" / "raw"
    for label in SHORTLIST:
        p = raw / f"{label}_10q_{ADS_PERIOD_END}.htm"
        ctxs, facts, texts = parse_ixbrl(p)
        print(f"\n=== {label}: {len(facts)} nonFraction, {len(texts)} nonNumeric, {len(ctxs)} contexts")
        axes = Counter()
        for c in ctxs.values():
            for a in c.typed:
                axes[("typed", a)] += 1
            for a in c.explicit:
                axes[("explicit", a)] += 1
        print("top axes:", axes.most_common(8))
        tagc = Counter(f.name for f in facts if f.context_ref in ctxs and ctxs[f.context_ref].dims
                       and any(k in f.name for k in ("Investment", "Principal", "Spread", "Maturity", "InterestRate")))
        for k, v in tagc.most_common(14):
            print("  ", v, k)
        tt = Counter(n for n, r, _ in texts if r in ctxs and ctxs[r].dims and "Investment" in n)
        print("  text:", tt.most_common(6))


def sigs() -> None:
    """Dimension signatures of fair value / principal facts and sample identifiers."""
    from collections import Counter
    from pipeline.ixbrl import parse_ixbrl, INVESTMENT_TAGS
    raw = Path(__file__).resolve().parent.parent / "fixtures" / "raw"
    for label in SHORTLIST:
        ctxs, facts, _ = parse_ixbrl(raw / f"{label}_10q_{ADS_PERIOD_END}.htm")
        print(f"\n=== {label}")
        for key in ("fair_value", "principal", "cost"):
            c = Counter()
            units = Counter()
            for f in facts:
                if f.name != INVESTMENT_TAGS[key]:
                    continue
                cx = ctxs.get(f.context_ref)
                if cx is None or cx.instant != ADS_PERIOD_END or "us-gaap:InvestmentIdentifierAxis" not in cx.typed:
                    continue
                c[tuple(sorted(cx.dims))] += 1
                units[f.unit] += 1
            print(key, dict(c.most_common(4)), "units", units.most_common(6))
        seen = []
        for cx in ctxs.values():
            v = cx.typed.get("us-gaap:InvestmentIdentifierAxis")
            if v and cx.instant == ADS_PERIOD_END and len(seen) < 4 and len(cx.dims) == 1:
                seen.append(v)
        for s in seen:
            print("  ID:", s[:230])


# Per-filer identifier parsers. ADS keeps the default in ixbrl.py.
def _filer_parsers() -> dict:
    from pipeline.ixbrl import split_pipe_identifier
    return {k: split_pipe_identifier for k in SHORTLIST}


LEGAL = {"inc", "llc", "lp", "ltd", "limited", "corp", "corporation", "co", "company", "holdings",
         "holding", "gmbh", "sarl", "sa", "bv", "plc", "ag", "llp", "l", "p", "pty", "ulc", "the",
         "fka", "dba", "aka"}


def norm_tokens(name: str) -> tuple[str, ...]:
    s = re.sub(r"\(.*?\)", " ", name.lower())  # drop parentheticals such as (f/k/a ...)
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    toks = [t for t in s.split() if t not in LEGAL]
    return tuple(toks)


def _unit(r: dict) -> str:
    # unit ref ids differ by filer: 'usd' (most), 'u_usd' (ADS)
    u = (r["principal_unit"] or "").lower()
    return u[2:] if u.startswith("u_") else u


def overlap() -> None:
    from collections import Counter
    from statistics import median
    from pipeline.ixbrl import parse_ixbrl, assemble_investments, summarize_parse
    raw = Path(__file__).resolve().parent.parent / "fixtures" / "raw"
    parsers = _filer_parsers()
    data = {}
    for label in ["ads"] + SHORTLIST:
        ctxs, facts, texts = parse_ixbrl(raw / f"{label}_10q_{ADS_PERIOD_END}.htm")
        kw = {} if label == "ads" else {"identifier_parser": parsers[label]}
        data[label] = assemble_investments(ctxs, facts, texts, ADS_PERIOD_END, **kw)
    ads_rows = [r for r in data["ads"] if r["principal"] is not None and r["fair_value"] is not None]
    ads_tok = {}  # tokens -> True if any ADS row for it has USD principal
    for r in ads_rows:
        t = norm_tokens(r["raw_name"])
        ads_tok[t] = ads_tok.get(t, False) or _unit(r) == "usd"

    def match(tok: tuple[str, ...]):
        # other filer name must equal a token suffix of the ADS name (ADS has an industry prefix)
        if len(tok) == 0 or len("".join(tok)) < 6:
            return None
        for a in ads_tok:
            if len(a) >= len(tok) and a[len(a) - len(tok):] == tok:
                return a
        return None

    print(f"{'filer':<28}{'sched':>6}{'parsed':>7}{'pct':>7}{'nonUSD':>7}{'ovl_all':>8}{'ovl_usd':>8}")
    for label in SHORTLIST + ["ads"]:
        rows = data[label]
        s = summarize_parse(rows)
        both = [r for r in rows if r["principal"] is not None and r["fair_value"] is not None]
        nonusd = [r for r in both if _unit(r) != "usd"]
        a_all, a_usd = set(), set()
        if label != "ads":
            for r in both:
                m = match(norm_tokens(r["raw_name"]))
                if m:
                    a_all.add(m)
                    if _unit(r) == "usd" and ads_tok[m]:
                        a_usd.add(m)
        eur = [float(r["fair_value"] / r["principal"]) for r in nonusd if _unit(r) == "eur" and r["principal"]]
        print(f"{label:<28}{s['schedule_rows']:>6}{len(both):>7}{s['pct']*100:>6.1f}%{len(nonusd):>7}"
              f"{len(a_all):>8}{len(a_usd):>8}")
        print("   non-USD units:", dict(Counter(_unit(r) for r in nonusd)),
              "EUR median FV/principal:", round(median(eur), 3) if eur else None)
        if label != "ads":
            print("   sample matches:", [" ".join(x) for x in list(a_all)[:3]])


if __name__ == "__main__":
    load_env()
    stage = sys.argv[1] if len(sys.argv) > 1 else "lookup"
    if stage == "overlap":
        overlap()
        sys.exit(0)
    if stage == "sigs":
        sigs()
        sys.exit(0)
    c = SecClient()
    if stage == "lookup":
        lookup(c)
    elif stage == "download":
        download(c)
    elif stage == "discover":
        discover()
    print("403s:", sum(1 for _, s in c.status_log if s == 403))
