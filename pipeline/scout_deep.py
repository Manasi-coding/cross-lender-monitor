"""Day 1 deep inspection: reconciliation, instrument type/maturity, negatives.
Read-only. No DB writes.

Run: python -m pipeline.scout_deep
"""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path

from pipeline.ixbrl import NS_IX, NS_XBRLI, parse_ixbrl, split_pipe_identifier, INVESTMENT_TAGS

RAW = Path(__file__).resolve().parent.parent / "fixtures" / "raw"
PE = "2026-06-30"
IDAX = "us-gaap:InvestmentIdentifierAxis"
FV_TAG = INVESTMENT_TAGS["fair_value"]   # us-gaap:InvestmentOwnedAtFairValue
COST_TAG = INVESTMENT_TAGS["cost"]
PRIN_TAG = INVESTMENT_TAGS["principal"]


# ---------------------------------------------------------------------------
# 1. Reconciliation
# ---------------------------------------------------------------------------
def recon(label: str) -> None:
    ctxs, facts, texts = parse_ixbrl(RAW / f"{label}_10q_{PE}.htm")

    # --- undimensioned instant facts whose name contains FairValue or Investment ---
    print(f"\n=== RECONCILIATION: {label}")
    nodim = [(f.name, f.value, f.context_ref) for f in facts
             if ("FairValue" in f.name or "Investment" in f.name)
             and f.value is not None
             and ctxs.get(f.context_ref)
             and ctxs[f.context_ref].instant == PE
             and not ctxs[f.context_ref].dims]
    name_sum = defaultdict(Decimal)
    for n, v, _ in nodim:
        name_sum[n] += v
    print("undimensioned facts at PE (distinct tags summed over their contexts):")
    for n, v in sorted(name_sum.items(), key=lambda x: abs(x[1]), reverse=True):
        print(f"  {n:75s}  {v:>22,.0f}")

    # --- schedule row sets ---
    by = {}
    for f in facts:
        c = ctxs.get(f.context_ref)
        if c and c.instant == PE and IDAX in c.typed and len(c.dims) == 1:
            by.setdefault(c.typed[IDAX], {})[f.name] = (by.get(c.typed[IDAX], {}).get(f.name)
                                                          or f.value)
    sched = {i: t for i, t in by.items() if FV_TAG in t or COST_TAG in t}
    fv_all   = sum((t.get(FV_TAG) or Decimal(0)) for t in sched.values())
    fv_neg   = sum((t[FV_TAG]     or Decimal(0)) for t in sched.values()
                   if FV_TAG in t and t[FV_TAG] and t[FV_TAG] < 0)
    fv_noprin = sum((t.get(FV_TAG) or Decimal(0)) for t in sched.values()
                    if FV_TAG in t and PRIN_TAG not in t)

    # filing total
    total_fv = name_sum.get(FV_TAG, Decimal(0))

    print(f"\nschedule rows: {len(sched)}")
    print(f"fv_all (all sched rows)     = {fv_all:>22,.0f}")
    print(f"fv_neg (negatives)          = {fv_neg:>22,.0f}")
    print(f"fv_no_principal             = {fv_noprin:>22,.0f}")
    print(f"filing total FV (nodim)     = {total_fv:>22,.0f}")
    print(f"raw gap (all - total)       = {fv_all - total_fv:>22,.0f}")

    # (a) cash equivalents / money market
    cash_ids = [i for i in sched if any(w in i.lower() for w in
                ("cash", "money market", "short-term", "treasury", "t-bill", "fund"))]
    fv_cash = sum((sched[i].get(FV_TAG) or Decimal(0)) for i in cash_ids)
    print(f"\n(a) cash/money-market ids: {len(cash_ids)}  FV sum={fv_cash:,.0f}")
    for i in cash_ids[:5]:
        print(f"    {i[:90]!r}  fv={sched[i].get(FV_TAG)}")

    # (b) duplicate identifiers: same base name in more than one period context
    base_count = Counter()
    for c in ctxs.values():
        v = c.typed.get(IDAX)
        if v and c.instant == PE:
            base_count[v] += 1
    dups = {k: v for k, v in base_count.items() if v > 1}
    print(f"\n(b) identifiers appearing in >1 instant context: {len(dups)}")
    for k, v in list(dups.items())[:4]:
        print(f"    {k[:80]!r}  count={v}")

    # (c) negative FV rows
    neg_rows = [(i, t[FV_TAG]) for i, t in sched.items()
                if FV_TAG in t and t[FV_TAG] is not None and t[FV_TAG] < 0]
    fv_neg_sum = sum(v for _, v in neg_rows)
    print(f"\n(c) negative FV rows: {len(neg_rows)}  sum={fv_neg_sum:,.0f}")
    for i, v in neg_rows[:5]:
        print(f"    {i[:80]!r}  fv={v}")

    # adjusted gap
    gap_adj = fv_all - fv_neg_sum - fv_cash - total_fv
    print(f"\ngap after removing negatives + cash: {fv_all - fv_neg_sum - fv_cash:,.0f} - {total_fv:,.0f} = {gap_adj:,.0f}")

    # residual: equity rows (no principal)
    print(f"gap after also removing no-principal rows: {fv_all - fv_neg_sum - fv_cash - fv_noprin:,.0f} - {total_fv:,.0f} = "
          f"{fv_all - fv_neg_sum - fv_cash - fv_noprin - total_fv:,.0f}")


# ---------------------------------------------------------------------------
# 2 & 3. Instrument type / maturity XBRL location
# ---------------------------------------------------------------------------
def type_maturity(label: str) -> None:
    from lxml import etree
    ctxs, facts, texts = parse_ixbrl(RAW / f"{label}_10q_{PE}.htm")

    print(f"\n=== TYPE/MATURITY XBRL: {label}")

    # all nonNumeric tag names and counts (total and on schedule contexts)
    nn_all = Counter()
    nn_sched = Counter()
    for n, r, _ in texts:
        nn_all[n] += 1
        c = ctxs.get(r)
        if c and (c.instant == PE or c.end == PE) and c.dims:
            nn_sched[n] += 1
    print("all nonNumeric tags (count):")
    for k, v in nn_all.most_common(30):
        s = nn_sched.get(k, 0)
        print(f"  {k:75s}  total={v}  on_sched={s}")

    # explicit axes on contexts that have InvestmentIdentifierAxis (schedule contexts)
    axis_counts = Counter()
    for c in ctxs.values():
        if IDAX not in c.typed:
            continue
        for a in c.explicit:
            axis_counts[a] += 1
        for a in c.typed:
            if a != IDAX:
                axis_counts[f"typed:{a}"] += 1
    print("explicit / extra-typed axes on identifier contexts:")
    for a, n in axis_counts.most_common(15):
        print(f"  {a}  count={n}")

    # any nonNumeric facts on identifier contexts or on contexts sharing the same identifier
    nn_on_id = [(n, r, t) for n, r, t in texts
                if ctxs.get(r) and IDAX in ctxs[r].typed]
    print(f"nonNumeric facts on identifier contexts: {len(nn_on_id)}")
    for n, r, t in nn_on_id[:10]:
        print(f"  {n}  val={t[:60]!r}")

    # look for InvestmentType or Maturity explicit member on schedule contexts
    type_axis_hits = [(c.typed.get(IDAX), c.explicit) for c in ctxs.values()
                      if IDAX in c.typed and c.explicit]
    print(f"identifier contexts that ALSO have explicit dims: {len(type_axis_hits)}")
    for ident, ex in type_axis_hits[:5]:
        print(f"  id={ident[:60]!r}  explicit={ex}")

    # search HTML for 'Maturity' table header and sample rows with dates
    p = RAW / f"{label}_10q_{PE}.htm"
    from lxml import etree
    tree = etree.parse(str(p), etree.XMLParser(huge_tree=True, recover=True))
    root = tree.getroot()
    import re
    sample_rows = 0
    for tr in root.iter():
        if not isinstance(tr.tag, str):
            continue
        ln = tr.tag.split("}")[-1].lower()
        if ln == "tr":
            t = " ".join("".join(tr.itertext()).split())
            if re.search(r"20[23]\d", t) and any(w in t for w in ("First lien", "Second lien", "Revolver", "Delayed draw", "Subordinated")):
                if sample_rows < 3:
                    print(f"  HTML row: {t[:200]}")
                sample_rows += 1
    print(f"  HTML rows with year+instrument-type text: {sample_rows}")


# ---------------------------------------------------------------------------
# 4. Negative cost / fair value with principal present
# ---------------------------------------------------------------------------
def negatives(label: str) -> None:
    ctxs, facts, _ = parse_ixbrl(RAW / f"{label}_10q_{PE}.htm")
    by = {}
    for f in facts:
        c = ctxs.get(f.context_ref)
        if c and c.instant == PE and IDAX in c.typed and len(c.dims) == 1:
            by.setdefault(c.typed[IDAX], {})[f.name] = (
                by.get(c.typed[IDAX], {}).get(f.name) or f.value)
    rows = [(i, t) for i, t in by.items() if PRIN_TAG in t]
    neg_cost = [(i, t) for i, t in rows if COST_TAG in t and t[COST_TAG] is not None and t[COST_TAG] < 0]
    neg_fv   = [(i, t) for i, t in rows if FV_TAG  in t and t[FV_TAG]  is not None and t[FV_TAG]  < 0]
    print(f"\n=== NEGATIVES: {label}")
    print(f"rows with principal + negative cost: {len(neg_cost)}")
    for i, t in neg_cost[:5]:
        print(f"  {i[:70]!r}  prin={t[PRIN_TAG]}  cost={t[COST_TAG]}  fv={t.get(FV_TAG)}")
    print(f"rows with principal + negative fv: {len(neg_fv)}")
    for i, t in neg_fv[:5]:
        print(f"  {i[:70]!r}  prin={t[PRIN_TAG]}  cost={t.get(COST_TAG)}  fv={t[FV_TAG]}")


if __name__ == "__main__":
    for lab in ("hps_corporate_lending", "blue_owl_credit_income"):
        recon(lab)
    for lab in ("hps_corporate_lending", "blue_owl_credit_income", "blackstone_secured_lending"):
        type_maturity(lab)
    for lab in ("hps_corporate_lending", "blue_owl_credit_income"):
        negatives(lab)
