"""tuning_report.py: read-only look at the diagnostic tuning labels (SPEC 12.6). It exists to find normalization
bugs. It reads no threshold, writes nothing, and its connection is opened read only.

Run: python -m pipeline.tuning_report
Prints: label counts for TUNING, the same split by BDC pair, and every pair the matcher put in AUTO that you labeled
NO_MATCH or UNSURE, with both raw names and both normalized names. AUTO is candidate_pairs.status = 'AUTO'; a pair
whose status was changed in the review queue is not listed here.
"""
from __future__ import annotations

import os
import sys
from collections import Counter

import psycopg

from pipeline.config import load_config, load_env_file

LABELS = ("MATCH", "NO_MATCH", "UNSURE")

ROWS_SQL = (
    "SELECT l.label, na.bdc_cik, nb.bdc_cik, ra.portfolio_company_raw, rb.portfolio_company_raw, "
    "na.borrower_normalized, nb.borrower_normalized, c.status, c.score "
    "FROM labeled_pairs l JOIN label_samples s ON s.sample_id = l.sample_id "
    "JOIN normalized_holdings na ON na.holding_id = l.holding_id_a JOIN normalized_holdings nb ON nb.holding_id = l.holding_id_b "
    "JOIN raw_holdings ra ON ra.holding_id = l.holding_id_a JOIN raw_holdings rb ON rb.holding_id = l.holding_id_b "
    "LEFT JOIN candidate_pairs c ON c.holding_id_a = l.holding_id_a AND c.holding_id_b = l.holding_id_b "
    "WHERE s.phase = 'TUNING' ORDER BY s.draw_order"
)


def fmt(counter: Counter) -> str:
    return ", ".join(f"{k} {counter.get(k, 0)}" for k in LABELS) + f" (total {sum(counter.values())})"


def main(argv: list[str] | None = None) -> int:
    load_env_file()
    short = {f["cik"]: key.upper() for key, f in load_config()["filers"].items()}
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        conn.read_only = True
        drawn = conn.execute("SELECT count(*) FROM label_samples WHERE phase = 'TUNING'").fetchone()[0]
        rows = conn.execute(ROWS_SQL).fetchall()
    print(f"tuning samples drawn {drawn}, labeled {len(rows)}, unlabeled {drawn - len(rows)}")
    print("labels: " + fmt(Counter(r[0] for r in rows)))
    by_pair: dict[str, Counter] = {}
    for r in rows:
        key = " / ".join(sorted((short.get(r[1], r[1]), short.get(r[2], r[2]))))
        by_pair.setdefault(key, Counter())[r[0]] += 1
    print("by BDC pair:")
    for key in sorted(by_pair):
        print(f"  {key}: " + fmt(by_pair[key]))
    bad = [r for r in rows if r[7] == "AUTO" and r[0] in ("NO_MATCH", "UNSURE")]
    print(f"AUTO pairs labeled NO_MATCH or UNSURE: {len(bad)}")
    for r in bad:
        print(f"  {r[0]} | score {r[8]}")
        print(f"      A [{short.get(r[1], r[1])}] {r[3]}  ->  {r[5]!r}")
        print(f"      B [{short.get(r[2], r[2])}] {r[4]}  ->  {r[6]!r}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
