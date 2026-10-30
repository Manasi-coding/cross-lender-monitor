"""block.py: blocking keys and the candidate predicate (phase_wise.md 6.2, SPEC 12.4 and 12.9).

Run: python -m pipeline.block
A pair is a candidate when all of these hold: same period_end_date, different bdc_cik, same instrument type that
is neither OTHER nor EQUITY, at least one shared block key, maturities within maturity_window_months when both
are present, total spreads within spread_window_bps when both are present. A NULL on either side skips that one
gate. Only the measured period is ever blocked. The same predicate is exposed as is_candidate() so
blocking_recall.py can ask "would blocking have paired these".
"""
from __future__ import annotations

import calendar
import json
import sys
import time
from collections import Counter
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import psycopg

from pipeline.config import load_config, load_env_file, resolve_period
from pipeline.normalize import refuse_if_frozen

NOT_CANDIDATE_TYPES = ("OTHER", "EQUITY")
RUN_TIMES = Path(__file__).resolve().parent.parent / "docs" / "run_times.jsonl"


def block_keys(period: date, type_norm: str, name: str, cfg: dict) -> list[str]:
    """(period, type, first name_prefix_chars of the name) and (period, type, first token of the name)."""
    n = cfg["blocking"]["name_prefix_chars"]
    first_token = name.split()[0] if name.split() else ""
    return [f"{period.isoformat()}|{type_norm}|{name[:n]}", f"{period.isoformat()}|{type_norm}|{first_token}"]


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.year * 12 + (d.month - 1) + months, 12)
    return date(y, m + 1, min(d.day, calendar.monthrange(y, m + 1)[1]))


def is_candidate(a: dict, b: dict, cfg: dict) -> bool:
    """The blocking predicate on two normalized rows (dicts with the normalized_holdings columns)."""
    bl = cfg["blocking"]
    if a["period_end_date"] != b["period_end_date"] or a["bdc_cik"] == b["bdc_cik"]:
        return False
    if a["instrument_type_norm"] != b["instrument_type_norm"] or a["instrument_type_norm"] in NOT_CANDIDATE_TYPES:
        return False
    ka = set(block_keys(a["period_end_date"], a["instrument_type_norm"], a["borrower_normalized"], cfg))
    kb = set(block_keys(b["period_end_date"], b["instrument_type_norm"], b["borrower_normalized"], cfg))
    if not ka & kb:
        return False
    if a["maturity_date"] is not None and b["maturity_date"] is not None:
        w = bl["maturity_window_months"]
        if not add_months(a["maturity_date"], -w) <= b["maturity_date"] <= add_months(a["maturity_date"], w):
            return False
    if a["spread_bps"] is not None and b["spread_bps"] is not None:
        if abs(Decimal(a["spread_bps"]) - Decimal(b["spread_bps"])) > Decimal(str(bl["spread_window_bps"])):
            return False
    return True


def build_block_keys(conn, period: date, cfg: dict) -> int:
    """Rewrite blocking_keys for the period from normalized_holdings. Returns the number of key rows."""
    rows = conn.execute(
        "SELECT holding_id, instrument_type_norm, borrower_normalized FROM normalized_holdings "
        "WHERE period_end_date = %s AND instrument_type_norm <> ALL(%s) ORDER BY holding_id",
        (period, list(NOT_CANDIDATE_TYPES))).fetchall()
    keys = [(hid, k) for hid, t, nm in rows for k in block_keys(period, t, nm, cfg)]
    with conn.transaction():
        conn.execute("DELETE FROM blocking_keys WHERE holding_id IN "
                     "(SELECT holding_id FROM normalized_holdings WHERE period_end_date = %s)", (period,))
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO blocking_keys (holding_id, block_key) VALUES (%s, %s)", keys)
    return len(keys)


CANDIDATE_SQL = """
SELECT DISTINCT ka.holding_id, kb.holding_id
FROM blocking_keys ka
JOIN blocking_keys kb ON kb.block_key = ka.block_key AND ka.holding_id < kb.holding_id
JOIN normalized_holdings a ON a.holding_id = ka.holding_id
JOIN normalized_holdings b ON b.holding_id = kb.holding_id
WHERE a.period_end_date = %(period)s AND b.period_end_date = a.period_end_date
  AND a.bdc_cik <> b.bdc_cik
  AND a.instrument_type_norm = b.instrument_type_norm
  AND a.instrument_type_norm <> ALL(%(skip)s)
  AND (a.maturity_date IS NULL OR b.maturity_date IS NULL
       OR b.maturity_date BETWEEN a.maturity_date - make_interval(months => %(months)s)
                              AND a.maturity_date + make_interval(months => %(months)s))
  AND (a.spread_bps IS NULL OR b.spread_bps IS NULL OR abs(a.spread_bps - b.spread_bps) <= %(spread)s)
ORDER BY 1, 2
"""


def candidate_pairs(conn, period: date, cfg: dict) -> list[tuple[int, int]]:
    bl = cfg["blocking"]
    return [(a, b) for a, b in conn.execute(CANDIDATE_SQL, {
        "period": period, "skip": list(NOT_CANDIDATE_TYPES), "months": bl["maturity_window_months"],
        "spread": bl["spread_window_bps"]}).fetchall()]


def all_pairs(counts: list[int]) -> int:
    """Cross-BDC pairs from per-BDC holding counts, the sum of n_i * n_j over BDC pairs, without enumerating."""
    total = sum(counts)
    return (total * total - sum(c * c for c in counts)) // 2


def efficiency(conn, period: date) -> dict:
    counts = [r[1] for r in conn.execute(
        "SELECT bdc_cik, count(*) FROM normalized_holdings WHERE period_end_date = %s GROUP BY bdc_cik ORDER BY bdc_cik",
        (period,)).fetchall()]
    allp = all_pairs(counts)
    cand = conn.execute(
        "SELECT count(*) FROM candidate_pairs c JOIN normalized_holdings a ON a.holding_id = c.holding_id_a "
        "WHERE a.period_end_date = %s", (period,)).fetchone()[0]
    share = (cand / allp) if allp else 0.0
    return {"holdings_per_bdc": counts, "all_pairs": allp, "candidate_pairs": cand,
            "candidate_share": share, "pairs_avoided_pct": 100 * (1 - share)}


def append_run_time(module: str, seconds: float, period: date) -> None:
    """One JSON line per run: module, seconds, period, config hash, git sha. The config hash and the git sha
    are null until the freeze tooling exists (pipeline.config has no hash code yet)."""
    RUN_TIMES.parent.mkdir(parents=True, exist_ok=True)
    line = {"module": module, "seconds": round(seconds, 3), "period": period.isoformat(),
            "config_hash": None, "git_sha": None, "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with open(RUN_TIMES, "a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n")


def main(argv: list[str] | None = None) -> int:
    import argparse
    import os
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", help="period end to block (YYYY-MM-DD); default MEASURED_PERIOD_END. Another period is an out-of-time run, decided with the freeze.")
    args = ap.parse_args(argv)
    load_env_file()
    period, cfg = resolve_period(args.period), load_config()
    t0 = time.perf_counter()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        refuse_if_frozen(conn, "block")
        n_keys = build_block_keys(conn, period, cfg)
        sizes = Counter(r[0] for r in conn.execute(
            "SELECT block_key FROM blocking_keys k JOIN normalized_holdings n USING (holding_id) "
            "WHERE n.period_end_date = %s", (period,)).fetchall())
        pairs = candidate_pairs(conn, period, cfg)
        seconds = time.perf_counter() - t0
        warn = cfg["blocking"]["max_block_size_warn"]
        print(f"period {period}: {n_keys} block key rows, {len(sizes)} distinct blocks, {len(pairs)} candidate pairs "
              f"(not stored here; match.py stores them with their scores)")
        top = sizes.most_common(5)
        print("largest blocks:", ", ".join(f"{k} = {v}" for k, v in top))
        big = [(k, v) for k, v in sizes.items() if v > warn]
        print(f"blocks larger than {warn}: {len(big)}" + ("  WARNING: " + "; ".join(f"{k} = {v}" for k, v in big[:5]) if big else ""))
        counts = conn.execute(
            "SELECT bdc_cik, count(*) FROM normalized_holdings WHERE period_end_date = %s GROUP BY bdc_cik ORDER BY bdc_cik",
            (period,)).fetchall()
        allp = all_pairs([c for _, c in counts])
        print(f"all_pairs (sum of n_i * n_j over BDC pairs, per-BDC counts {[c for _, c in counts]}): {allp}")
        print(f"candidate pairs from blocking: {len(pairs)}  share {len(pairs) / allp:.4%}  pairs avoided {100 * (1 - len(pairs) / allp):.2f}%  (report only)")
    append_run_time("block", seconds, period)
    print(f"block.py wall clock {seconds:.2f}s appended to {RUN_TIMES.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
