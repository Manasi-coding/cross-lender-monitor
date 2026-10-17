"""match.py: score every candidate pair and write candidate_pairs (phase_wise.md 6.3 and 6.4).

Run: python -m pipeline.match [--eyeball N]
score = token_sort_ratio(a_norm, b_norm) / 100 on the normalized names only (maturity, spread and type decide
candidacy in block.py, not the score). Digit guard: if the multisets of digit tokens in the two names differ,
the score is capped at review_min - 0.01, so "acme holdings 2" and "acme holdings" never reach AUTO.
Status: AUTO at auto_min or above, REVIEW from review_min (inclusive) up to auto_min, else NO_MATCH.
Every candidate pair is written, NO_MATCH included, with holding_id_a < holding_id_b.
Re-running recomputes AUTO, REVIEW and NO_MATCH rows, deletes such rows that are no longer candidates, and
leaves CONFIRMED and REJECTED rows alone. Refuses to run once the matcher is frozen.
"""
from __future__ import annotations

import random
import re
import sys
import time
from collections import Counter
from datetime import date
from decimal import ROUND_HALF_EVEN, Decimal

import psycopg
from rapidfuzz import fuzz

from pipeline.block import RUN_TIMES, all_pairs, append_run_time, candidate_pairs, efficiency
from pipeline.config import load_config, load_env_file, measured_period_end
from pipeline.normalize import refuse_if_frozen

_Q = Decimal("0.00000001")
_DIGITS = re.compile(r"\d+")


def thresholds(cfg: dict) -> dict[str, Decimal]:
    b = cfg["bands"]
    return {k: Decimal(str(b[k])) for k in ("auto_min", "review_min", "just_below_min")}


def digit_tokens(name: str) -> Counter:
    return Counter(_DIGITS.findall(name))


def score_pair(a_name: str, b_name: str, cfg: dict) -> Decimal:
    th = thresholds(cfg)
    score = (Decimal(repr(fuzz.token_sort_ratio(a_name, b_name))) / 100).quantize(_Q, rounding=ROUND_HALF_EVEN)
    if digit_tokens(a_name) != digit_tokens(b_name):
        score = min(score, th["review_min"] - Decimal("0.01"))
    return score


def status_for(score: Decimal, cfg: dict) -> str:
    th = thresholds(cfg)
    if score >= th["auto_min"]:
        return "AUTO"
    if score >= th["review_min"]:       # 0.80 is inclusive
        return "REVIEW"
    return "NO_MATCH"


def band_for(score: Decimal, cfg: dict) -> str:
    th = thresholds(cfg)
    if score >= th["auto_min"]:
        return "AUTO"
    if score >= th["review_min"]:
        return "REVIEW"
    return "JUST_BELOW" if score >= th["just_below_min"] else "LOW"


def run(conn, period: date, cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    refuse_if_frozen(conn, "match")
    eligible, keyed = conn.execute(
        "SELECT count(*) FILTER (WHERE n.instrument_type_norm <> ALL(%s)), "
        "count(DISTINCT k.holding_id) FROM normalized_holdings n LEFT JOIN blocking_keys k USING (holding_id) "
        "WHERE n.period_end_date = %s", (["OTHER", "EQUITY"], period)).fetchone()
    if eligible and not keyed:
        raise SystemExit("match refuses to run: blocking_keys is empty for this period. Run block.py first.")
    pairs = candidate_pairs(conn, period, cfg)
    ids = sorted({i for p in pairs for i in p})
    names = dict(conn.execute("SELECT holding_id, borrower_normalized FROM normalized_holdings "
                              "WHERE holding_id = ANY(%s)", (ids,)).fetchall())
    scored = []
    for a, b in pairs:
        s = score_pair(names[a], names[b], cfg)
        scored.append((a, b, s, status_for(s, cfg)))
    keep = {(a, b) for a, b, _, _ in scored}
    with conn.transaction():
        existing = conn.execute(
            "SELECT c.holding_id_a, c.holding_id_b FROM candidate_pairs c JOIN normalized_holdings n ON n.holding_id = c.holding_id_a "
            "WHERE n.period_end_date = %s AND c.status IN ('AUTO','REVIEW','NO_MATCH')", (period,)).fetchall()
        gone = [(a, b) for a, b in existing if (a, b) not in keep]
        with conn.cursor() as cur:
            cur.executemany("DELETE FROM candidate_pairs WHERE holding_id_a = %s AND holding_id_b = %s "
                            "AND status IN ('AUTO','REVIEW','NO_MATCH')", gone)
            cur.executemany(
                "INSERT INTO candidate_pairs (holding_id_a, holding_id_b, score, status) VALUES (%s, %s, %s, %s) "
                "ON CONFLICT (holding_id_a, holding_id_b) DO UPDATE SET score = EXCLUDED.score, status = EXCLUDED.status, "
                "updated_at = now() WHERE candidate_pairs.status IN ('AUTO','REVIEW','NO_MATCH') "
                "AND (candidate_pairs.score, candidate_pairs.status) IS DISTINCT FROM (EXCLUDED.score, EXCLUDED.status)",
                scored)
    bands = Counter(band_for(s, cfg) for _, _, s, _ in scored)
    exact = [(a, b, s, st) for a, b, s, st in scored if names[a] == names[b]]
    return {"scored": scored, "bands": bands, "exact": exact, "deleted": len(gone), "names": names}


def eyeball(conn, period: date, n: int, seed: int) -> None:
    rows = conn.execute(
        "SELECT c.holding_id_a, c.holding_id_b, c.score, a.instrument_type_norm, a.maturity_date, b.maturity_date, "
        "a.spread_bps, b.spread_bps, ra.portfolio_company_raw, rb.portfolio_company_raw, fa.bdc_name, fb.bdc_name, "
        "a.borrower_normalized, b.borrower_normalized "
        "FROM candidate_pairs c "
        "JOIN normalized_holdings a ON a.holding_id = c.holding_id_a JOIN normalized_holdings b ON b.holding_id = c.holding_id_b "
        "JOIN raw_holdings ra ON ra.holding_id = a.holding_id JOIN raw_holdings rb ON rb.holding_id = b.holding_id "
        "JOIN raw_filings fa ON fa.filing_id = ra.filing_id JOIN raw_filings fb ON fb.filing_id = rb.filing_id "
        "WHERE c.status = 'AUTO' AND a.period_end_date = %s ORDER BY c.holding_id_a, c.holding_id_b", (period,)).fetchall()
    pick = random.Random(seed).sample(rows, min(n, len(rows)))
    print(f"\n== {len(pick)} of {len(rows)} AUTO pairs, random.Random({seed}).sample")
    for i, r in enumerate(pick, 1):
        print(f"{i:>2}. score {r[2]:.4f} | {r[3]} | maturity {r[4]} / {r[5]} | spread_bps {r[6]} / {r[7]}")
        print(f"      A [{r[10][:22]}] {r[8][:90]}")
        print(f"      B [{r[11][:22]}] {r[9][:90]}")
        print(f"      normalized: {r[12]!r} | {r[13]!r}")


def list_non_auto(conn, period: date) -> None:
    """Print every REVIEW and NO_MATCH (JUST_BELOW and LOW) pair with both names, so normalization failures show."""
    rows = conn.execute(
        "SELECT c.score, c.status, a.instrument_type_norm, a.maturity_date, b.maturity_date, a.spread_bps, b.spread_bps, "
        "ra.portfolio_company_raw, rb.portfolio_company_raw, a.borrower_normalized, b.borrower_normalized, "
        "fa.bdc_name, fb.bdc_name "
        "FROM candidate_pairs c "
        "JOIN normalized_holdings a ON a.holding_id = c.holding_id_a JOIN normalized_holdings b ON b.holding_id = c.holding_id_b "
        "JOIN raw_holdings ra ON ra.holding_id = a.holding_id JOIN raw_holdings rb ON rb.holding_id = b.holding_id "
        "JOIN raw_filings fa ON fa.filing_id = ra.filing_id JOIN raw_filings fb ON fb.filing_id = rb.filing_id "
        "WHERE c.status <> 'AUTO' AND a.period_end_date = %s ORDER BY c.score DESC, c.holding_id_a, c.holding_id_b", (period,)).fetchall()
    th = thresholds(load_config())
    print(f"\n== {len(rows)} non-AUTO candidate pairs (score order)")
    for r in rows:
        band = "REVIEW" if r[0] >= th["review_min"] else ("JUST_BELOW" if r[0] >= th["just_below_min"] else "LOW")
        paren = "  [PARENTHETICAL IN RAW NAME]" if "(" in r[7] or "(" in r[8] else ""
        print(f"{band:<10} {r[0]:.4f} | {r[2]} | maturity {r[3]} / {r[4]} | spread {r[5]} / {r[6]}{paren}")
        print(f"      A [{r[11][:3]}] {r[7][:80]}   -> {r[9]!r}")
        print(f"      B [{r[12][:3]}] {r[8][:80]}   -> {r[10]!r}")


def main(argv: list[str] | None = None) -> int:
    import argparse
    import os
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-non-auto", action="store_true", help="print every non-AUTO candidate pair")
    ap.add_argument("--eyeball", type=int, default=0, help="print N random AUTO pairs (seed from sampling.seed)")
    args = ap.parse_args(argv)
    load_env_file()
    period, cfg = measured_period_end(), load_config()
    t0 = time.perf_counter()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        res = run(conn, period, cfg)
        seconds = time.perf_counter() - t0
        th = thresholds(cfg)
        b = res["bands"]
        print(f"scored {len(res['scored'])} candidate pairs (deleted {res['deleted']} rows that are no longer candidates)")
        print(f"bands: AUTO (>= {th['auto_min']}) {b['AUTO']}, REVIEW ({th['review_min']} to < {th['auto_min']}) {b['REVIEW']}, "
              f"JUST_BELOW ({th['just_below_min']} to < {th['review_min']}) {b['JUST_BELOW']}, LOW (< {th['just_below_min']}) {b['LOW']}; "
              f"NO_MATCH = {b['JUST_BELOW'] + b['LOW']}")
        exact = res["exact"]
        print(f"exact-match baseline (candidate pairs with equal normalized names): {len(exact)}, of which AUTO {sum(1 for e in exact if e[3] == 'AUTO')}; "
              f"scorer AUTO {b['AUTO']}, AUTO + REVIEW {b['AUTO'] + b['REVIEW']}")
        eff = efficiency(conn, period)
        print(f"blocking efficiency (report only): holdings per BDC {eff['holdings_per_bdc']}, all_pairs {eff['all_pairs']}, "
              f"candidate_pairs {eff['candidate_pairs']}, candidate share {eff['candidate_share']:.4%}, pairs avoided {eff['pairs_avoided_pct']:.2f}%")
        if args.eyeball:
            eyeball(conn, period, args.eyeball, cfg["sampling"]["seed"])
        if args.list_non_auto:
            list_non_auto(conn, period)
    append_run_time("match", seconds, period)
    print(f"\nmatch.py wall clock {seconds:.2f}s appended to {RUN_TIMES.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
