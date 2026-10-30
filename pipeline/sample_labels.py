"""sample_labels.py: draw the pairs you will label (SPEC 12.6, phase_wise.md 6.6).

Run: python -m pipeline.sample_labels --phase tuning [--redraw]
Tuning: sampling.tuning_size pairs, drawn at random (random.Random(sampling.seed)) from ALL candidate_pairs of
MEASURED_PERIOD_END, any status, no stratification. The score is never read. Rows go to label_samples with
phase TUNING, score_band NULL, holding_id_a < holding_id_b and draw_order a random permutation (1 to n).
Re-running does nothing once a tuning draw exists. --redraw replaces the tuning samples only if none is labeled.

Run: python -m pipeline.sample_labels --phase heldout [--redraw]
Held-out (SPEC 12.6, phase_wise.md 6.6): refuses unless a matcher_freeze row exists and the current matcher hash equals it.
Frame: candidate pairs whose two holdings are both in MEASURED_PERIOD_END, minus the tuning pairs. A pair's band comes from its
stored score and the frozen band edges, never from candidate_pairs.status. AUTO gets sampling.heldout_auto pairs and every other
band min(sampling.heldout_per_band, band size), so a small band is labeled in full. Each band is drawn with
random.Random("<heldout_seed>:<band>") and the draw order is a random permutation over all drawn pairs, so the order leaks no
band. label_samples gets phase HELDOUT and the band; band_sizes gets the frame size (the N_b of the weighted formulas), the sample
size and the matcher hash. Re-running changes nothing. --redraw replaces the draw only while no held-out pair is labeled.
Only counts are printed: no pair, holding or name.

Run: python -m pipeline.sample_labels --phase outoftime [--redraw]
Out-of-time sample (migration 010): the same freeze and hash check, then candidate pairs of sampling.outoftime_period (the prior
quarter, never the measured period) by stored score, min(cap, band size) per band from sampling.outoftime_sizes, seed
sampling.outoftime_seed. label_samples gets phase OUTOFTIME and the band; outoftime_band_sizes gets the frame size, sample size,
period, seed and hash. The held-out draw also stores its seed in band_sizes.draw_seed.
"""
from __future__ import annotations

import os
import random
import sys
from datetime import date

import psycopg

from pipeline.config import REPO_ROOT, load_config, load_env_file, measured_period_end, require_frozen_matching
from pipeline.match import band_for

BANDS = ("AUTO", "REVIEW", "JUST_BELOW", "LOW")


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


def heldout_frame(conn, period: date, cfg: dict) -> dict[str, list[tuple[int, int]]]:
    """{band: [(holding_id_a, holding_id_b), ...] sorted}: candidate pairs of the period (both holdings in it) minus the tuning
    pairs, banded by the stored score. candidate_pairs.status is not read."""
    tuning = {(a, b) for a, b in conn.execute("SELECT holding_id_a, holding_id_b FROM label_samples WHERE phase = 'TUNING'").fetchall()}
    rows = conn.execute(
        "SELECT c.holding_id_a, c.holding_id_b, c.score FROM candidate_pairs c "
        "JOIN normalized_holdings a ON a.holding_id = c.holding_id_a JOIN normalized_holdings b ON b.holding_id = c.holding_id_b "
        "WHERE a.period_end_date = %s AND b.period_end_date = %s ORDER BY c.holding_id_a, c.holding_id_b", (period, period)).fetchall()
    frame: dict[str, list[tuple[int, int]]] = {b: [] for b in BANDS}
    for a, b, score in rows:
        if (a, b) not in tuning:
            frame[band_for(score, cfg)].append((a, b))
    return frame


def draw_heldout(conn, period: date, cfg: dict, root=REPO_ROOT, redraw: bool = False) -> dict:
    """The held-out draw. Returns {"status": "drawn" | "exists", "bands": {band: {"frame": n, "sample": n}}, "hash": ...}."""
    stored_hash = require_frozen_matching(conn, "the held-out draw", cfg, root)       # no freeze row, or a changed matcher: refuse
    s = cfg["sampling"]
    existing = conn.execute("SELECT count(*) FROM label_samples WHERE phase = 'HELDOUT'").fetchone()[0]
    sized = conn.execute("SELECT count(*) FROM band_sizes").fetchone()[0]
    if (existing or sized) and not redraw:
        return {"status": "exists", "existing": existing, "bands": {}, "hash": stored_hash}
    if redraw:
        labeled = conn.execute("SELECT count(*) FROM label_samples s JOIN labeled_pairs l USING (sample_id) WHERE s.phase = 'HELDOUT'").fetchone()[0]
        if labeled:
            raise SystemExit(f"--redraw refuses: {labeled} held-out pairs are already labeled. Only --unfreeze removes a labeled held-out set.")
    frame = heldout_frame(conn, period, cfg)
    seed = s["heldout_seed"]
    drawn: list[tuple[str, int, int]] = []
    bands = {}
    for band in BANDS:
        size = len(frame[band])
        k = min(s["heldout_auto"], size) if band == "AUTO" else min(s["heldout_per_band"], size)
        pick = random.Random(f"{seed}:{band}").sample(frame[band], k)
        drawn += [(band, a, b) for a, b in pick]
        bands[band] = {"frame": size, "sample": k}
    random.Random(f"{seed}:order").shuffle(drawn)                      # one permutation over all bands, so the order shows no band
    with conn.transaction():
        if redraw:
            conn.execute("DELETE FROM label_samples WHERE phase = 'HELDOUT'")
            conn.execute("DELETE FROM band_sizes")
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO label_samples (holding_id_a, holding_id_b, phase, score_band, draw_order) VALUES (%s, %s, 'HELDOUT', %s, %s)",
                            [(a, b, band, i) for i, (band, a, b) in enumerate(drawn, 1)])
            cur.executemany("INSERT INTO band_sizes (score_band, band_size, sample_size, matcher_config_hash, draw_seed) VALUES (%s, %s, %s, %s, %s)",
                            [(band, v["frame"], v["sample"], stored_hash, seed) for band, v in bands.items()])
    return {"status": "drawn", "bands": bands, "hash": stored_hash, "drawn": len(drawn)}


def draw_outoftime(conn, measured: date, cfg: dict, root=REPO_ROOT, redraw: bool = False) -> dict:
    """The out-of-time draw (phase OUTOFTIME). Same freeze and hash check as the held-out draw; never the measured period."""
    stored_hash = require_frozen_matching(conn, "the out-of-time draw", cfg, root)
    s = cfg["sampling"]
    period, seed, caps = date.fromisoformat(s["outoftime_period"]), s["outoftime_seed"], s["outoftime_sizes"]
    if period == measured:
        raise SystemExit(f"the out-of-time draw refuses: sampling.outoftime_period {period} is the measured period.")
    if set(caps) != set(BANDS):
        raise SystemExit(f"sampling.outoftime_sizes needs exactly the bands {list(BANDS)}.")
    existing = conn.execute("SELECT count(*) FROM label_samples WHERE phase = 'OUTOFTIME'").fetchone()[0]
    sized = conn.execute("SELECT count(*) FROM outoftime_band_sizes").fetchone()[0]
    if (existing or sized) and not redraw:
        return {"status": "exists", "existing": existing, "bands": {}, "hash": stored_hash, "period": period}
    if redraw:
        labeled = conn.execute("SELECT count(*) FROM label_samples s JOIN labeled_pairs l USING (sample_id) WHERE s.phase = 'OUTOFTIME'").fetchone()[0]
        if labeled:
            raise SystemExit(f"--redraw refuses: {labeled} out-of-time pairs are already labeled. Only --unfreeze removes a labeled out-of-time set.")
    frame = heldout_frame(conn, period, cfg)                                  # both holdings in the prior quarter, banded by stored score
    drawn: list[tuple[str, int, int]] = []
    bands = {}
    for band in BANDS:
        size = len(frame[band])
        k = min(caps[band], size)
        pick = random.Random(f"{seed}:{band}").sample(frame[band], k) if k else []
        drawn += [(band, a, b) for a, b in pick]
        bands[band] = {"frame": size, "sample": k}
    random.Random(f"{seed}:order").shuffle(drawn)
    with conn.transaction():
        if redraw:
            conn.execute("DELETE FROM label_samples WHERE phase = 'OUTOFTIME'")
            conn.execute("DELETE FROM outoftime_band_sizes")
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO label_samples (holding_id_a, holding_id_b, phase, score_band, draw_order) VALUES (%s, %s, 'OUTOFTIME', %s, %s)",
                            [(a, b, band, i) for i, (band, a, b) in enumerate(drawn, 1)])
            cur.executemany("INSERT INTO outoftime_band_sizes (score_band, band_size, sample_size, period_end_date, draw_seed, matcher_config_hash) VALUES (%s, %s, %s, %s, %s, %s)",
                            [(band, v["frame"], v["sample"], period, seed, stored_hash) for band, v in bands.items()])
    return {"status": "drawn", "bands": bands, "hash": stored_hash, "drawn": len(drawn), "period": period}


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", required=True, choices=["tuning", "heldout", "outoftime"])
    ap.add_argument("--redraw", action="store_true", help="replace the tuning samples, only if none is labeled")
    args = ap.parse_args(argv)
    load_env_file()
    period, cfg = measured_period_end(), load_config()
    if args.phase == "outoftime":
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            res = draw_outoftime(conn, period, cfg, redraw=args.redraw)
        if res["status"] == "exists":
            print(f"out-of-time draw already exists: {res['existing']} samples. Nothing changed.")
            return 0
        print(f"out-of-time draw for {res['period']}, matcher hash {res['hash']}, seed {cfg['sampling']['outoftime_seed']}: drew {res['drawn']} pairs")
        for band, v in res["bands"].items():
            print(f"  {band:<10} frame {v['frame']:>4}  drawn {v['sample']:>3}")
        return 0
    if args.phase == "heldout":
        with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
            res = draw_heldout(conn, period, cfg, redraw=args.redraw)
        if res["status"] == "exists":
            print(f"held-out draw already exists: {res['existing']} samples. Nothing changed.")
            return 0
        print(f"held-out draw for {period}, matcher hash {res['hash']}, seed {cfg['sampling']['heldout_seed']}: drew {res['drawn']} pairs")
        for band, v in res["bands"].items():
            print(f"  {band:<10} frame {v['frame']:>4}  drawn {v['sample']:>3}")
        return 0
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
