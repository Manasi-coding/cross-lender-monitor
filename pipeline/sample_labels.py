"""sample_labels.py: draw the pairs you will label (SPEC 12.6, phase_wise.md 6.6).

Run: python -m pipeline.sample_labels --phase tuning [--redraw]
Tuning: sampling.tuning_size pairs, drawn at random (random.Random(sampling.seed)) from ALL candidate_pairs of
MEASURED_PERIOD_END, any status, no stratification. The score is never read. Rows go to label_samples with
phase TUNING, score_band NULL, holding_id_a < holding_id_b and draw_order a random permutation (1 to n).
Re-running does nothing once a tuning draw exists. --redraw replaces the tuning samples only if none is labeled.
The held-out draw is built on Day 8 and is not available here.
"""
from __future__ import annotations

import os
import random
import sys
from datetime import date

import psycopg

from pipeline.config import load_config, load_env_file, measured_period_end


def draw_tuning(conn, period: date, cfg: dict, redraw: bool = False) -> dict:
    """Returns {"status": "drawn" | "exists", "drawn": n, "existing": n, "pool": n, "replaced": n}."""
    s = cfg["sampling"]
    if conn.execute("SELECT count(*) FROM band_sizes").fetchone()[0]:
        raise SystemExit("sample_labels refuses: band_sizes already has rows, so the held-out sample exists. "
                         "A new tuning pair could overlap it.")
    existing = conn.execute("SELECT count(*) FROM label_samples WHERE phase = 'TUNING'").fetchone()[0]
    replaced = 0
    if existing and not redraw:
        return {"status": "exists", "drawn": 0, "existing": existing, "pool": None, "replaced": 0}
    if existing and redraw:
        labeled = conn.execute("SELECT count(*) FROM label_samples s JOIN labeled_pairs l USING (sample_id) "
                               "WHERE s.phase = 'TUNING'").fetchone()[0]
        if labeled:
            raise SystemExit(f"--redraw refuses: {labeled} tuning samples are already labeled.")
    # the pool: every candidate pair whose holdings belong to the measured period. No status or score filter.
    pool = conn.execute(
        "SELECT c.holding_id_a, c.holding_id_b FROM candidate_pairs c "
        "JOIN normalized_holdings a ON a.holding_id = c.holding_id_a "
        "JOIN normalized_holdings b ON b.holding_id = c.holding_id_b "
        "WHERE a.period_end_date = %s AND b.period_end_date = %s ORDER BY c.holding_id_a, c.holding_id_b",
        (period, period)).fetchall()
    chosen = random.Random(s["seed"]).sample(pool, min(s["tuning_size"], len(pool)))   # a random order = the permutation
    with conn.transaction():
        if existing:
            replaced = conn.execute("DELETE FROM label_samples WHERE phase = 'TUNING'").rowcount
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO label_samples (holding_id_a, holding_id_b, phase, score_band, draw_order) "
                "VALUES (%s, %s, 'TUNING', NULL, %s)",
                [(a, b, i) for i, (a, b) in enumerate(chosen, 1)])
    return {"status": "drawn", "drawn": len(chosen), "existing": existing, "pool": len(pool), "replaced": replaced}


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=["tuning", "heldout"])
    ap.add_argument("--redraw", action="store_true", help="replace the tuning samples, only if none is labeled")
    args = ap.parse_args(argv)
    if args.phase == "heldout":
        print("The held-out draw is built on Day 8 and is not available yet.")
        return 2
    load_env_file()
    period, cfg = measured_period_end(), load_config()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        res = draw_tuning(conn, period, cfg, args.redraw)
    if res["status"] == "exists":
        print(f"tuning draw already exists: {res['existing']} samples. Nothing changed. Use --redraw to replace unlabeled samples.")
    else:
        note = f" (replaced {res['replaced']} unlabeled samples)" if res["replaced"] else ""
        print(f"drew {res['drawn']} tuning pairs for {period}, seed {cfg['sampling']['seed']}{note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
