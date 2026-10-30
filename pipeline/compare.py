"""compare.py: full deterministic rebuild of the curated tables (SPEC section 5, phase_wise.md 6.5).

Run: python -m pipeline.compare
Only the measured period (MEASURED_PERIOD_END) is built. One transaction: the API sees the old state or the new one.
Reads candidate_pairs, normalized_holdings, raw_holdings and raw_filings. Writes only the curated tables
(canonical_borrowers, canonical_facilities, holding_facility_map, facility_comparisons, facility_summary,
review_clusters, review_cluster_members). It never writes candidate_pairs, label_samples, labeled_pairs or
matcher_freeze, and no label feeds the clustering.

Steps:
1. Edges are AUTO and CONFIRMED pairs between different BDCs. REJECTED pairs are cannot-link constraints.
   Edges go in the order CONFIRMED first, then descending score, then ascending holding ids. An edge whose union
   would put a cannot-link pair into one component is skipped and logged. REVIEW and NO_MATCH never form edges.
2. A component of 2 or more holdings is a cluster. A cluster with two MARKED holdings (non-null fair_value_pct_par)
   from one BDC goes to review_clusters, with all its holdings as members. Holdings with an excluded_reason have no
   mark: they do not count for this test, and they stay in the cluster, in facility_comparisons with their reason,
   and in excluded_count.
3. A cluster becomes a facility only if at least 2 holdings have a non-null fair_value_pct_par.
4. A cluster is named by its most frequent borrower_normalized (ties: ascending codepoint order). Facilities are
   grouped into borrowers by exact equality of that name within the period.
5. Divergence is max minus min fair_value_pct_par over included holdings (Decimal), flagged from the config cutoffs.
   exposure_usd = divergence / 100 * the smallest principal among included holdings (v2 F1, a ranking key).
Rows are inserted in a fixed order and the sequences restart, so two runs give identical ids and rows.
"""
from __future__ import annotations

import os
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal

import psycopg

from pipeline.block import RUN_TIMES, append_run_time
from pipeline.config import load_config, load_env_file, measured_period_end

CURATED = ["facility_summary", "facility_comparisons", "holding_facility_map", "canonical_facilities",
           "canonical_borrowers", "review_cluster_members", "review_clusters"]    # delete order (children first)
SEQUENCES = [("canonical_borrowers", "canonical_borrower_id"), ("canonical_facilities", "facility_id"),
             ("review_clusters", "cluster_id")]


# ------------------------------------------------------------------ pure functions
def flag_for(divergence: Decimal, mild: Decimal, flagged: Decimal) -> str:
    """Under mild: AGREEMENT. From mild up to but not including flagged: MILD. flagged and above: FLAGGED."""
    if divergence < mild:
        return "AGREEMENT"
    if divergence < flagged:
        return "MILD"
    return "FLAGGED"


def exposure_usd(divergence_pts: Decimal, smallest_principal: Decimal) -> Decimal:
    """(divergence_pts / 100) * MIN(principal over included holdings). Included holdings have a non-null, nonzero USD principal."""
    return divergence_pts / Decimal(100) * smallest_principal


def cutoffs(cfg: dict) -> tuple[Decimal, Decimal]:
    d = cfg["divergence"]
    return Decimal(str(d["mild_pts"])), Decimal(str(d["flagged_pts"]))


def build_clusters(edges, bdc: dict[int, str], rejected) -> tuple[list[list[int]], list[dict]]:
    """edges: (holding_id_a, holding_id_b, score, status) for AUTO and CONFIRMED pairs. rejected: (a, b) pairs.
    Returns (clusters of 2 or more holding ids, each sorted; list of skipped edges with the reason)."""
    cannot: dict[int, set[int]] = defaultdict(set)
    for a, b in rejected:
        cannot[a].add(b)
        cannot[b].add(a)
    parent: dict[int, int] = {}
    members: dict[int, set[int]] = {}

    def find(x: int) -> int:
        if x not in parent:
            parent[x], members[x] = x, {x}
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    skipped = []
    ordered = sorted(edges, key=lambda e: (e[3] != "CONFIRMED", -e[2], e[0], e[1]))
    for a, b, score, status in ordered:
        if bdc[a] == bdc[b]:                                   # never clustered: same BDC pair
            skipped.append({"a": a, "b": b, "score": score, "status": status, "reason": "same BDC"})
            continue
        ra, rb = find(a), find(b)
        if ra == rb:
            continue
        hit = next(((m, n) for m in sorted(members[ra]) for n in sorted(cannot.get(m, ())) if n in members[rb]), None)
        if hit:
            skipped.append({"a": a, "b": b, "score": score, "status": status, "reason": f"cannot-link {hit[0]}-{hit[1]}"})
            continue
        if len(members[ra]) < len(members[rb]):
            ra, rb = rb, ra
        parent[rb] = ra
        members[ra] |= members.pop(rb)
    clusters = sorted((sorted(m) for m in members.values() if len(m) >= 2), key=lambda c: c[0])
    return clusters, skipped


def most_frequent(values):
    """Most frequent non-null value; ties go to the smallest. None if there is no value."""
    counts = Counter(v for v in values if v is not None)
    if not counts:
        return None
    top = max(counts.values())
    return min(v for v, c in counts.items() if c == top)


# ------------------------------------------------------------------ the rebuild
def run(conn, period: date, cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    mild, flagged = cutoffs(cfg)
    log: list[str] = []

    pairs = conn.execute(
        "SELECT c.holding_id_a, c.holding_id_b, c.score, c.status FROM candidate_pairs c "
        "JOIN normalized_holdings a ON a.holding_id = c.holding_id_a JOIN normalized_holdings b ON b.holding_id = c.holding_id_b "
        "WHERE a.period_end_date = %s AND b.period_end_date = %s ORDER BY c.holding_id_a, c.holding_id_b", (period, period)).fetchall()
    edges = [p for p in pairs if p[3] in ("AUTO", "CONFIRMED")]
    rejected = [(p[0], p[1]) for p in pairs if p[3] == "REJECTED"]

    ids = sorted({h for p in edges for h in p[:2]})
    rows = {r[0]: r for r in conn.execute(
        "SELECT n.holding_id, n.bdc_cik, f.bdc_name, n.borrower_normalized, n.instrument_type_norm, n.reference_rate, "
        "n.maturity_date, n.spread_bps, n.principal, n.fair_value_pct_par, n.excluded_reason, n.source_url "
        "FROM normalized_holdings n JOIN raw_holdings h ON h.holding_id = n.holding_id "
        "JOIN raw_filings f ON f.filing_id = h.filing_id WHERE n.holding_id = ANY(%s)", (ids,)).fetchall()}
    bdc = {i: r[1] for i, r in rows.items()}

    clusters, skipped = build_clusters(edges, bdc, rejected)
    for s in skipped:
        log.append(f"skipped edge {s['a']}-{s['b']} ({s['status']}, score {s['score']}): {s['reason']}")

    collisions, failed, facilities = [], [], []
    for members in clusters:
        marked = [m for m in members if rows[m][9] is not None]       # the collision test counts marked holdings only
        if len({bdc[m] for m in marked}) < len(marked):
            collisions.append(members)
            log.append(f"review cluster (same BDC collision): holdings {members}")
            continue
        usable = [m for m in members if rows[m][9] is not None]
        if len(usable) < 2:
            failed.append(members)
            log.append(f"not a facility, {len(usable)} usable mark(s): holdings {members}")
            continue
        facilities.append(members)

    def describe(members):
        name = most_frequent([rows[m][3] for m in members])
        types = {rows[m][4] for m in members}
        if len(types) > 1:
            log.append(f"warning: cluster {members} mixes instrument types {sorted(types)}")
        maturities = [rows[m][6] for m in members if rows[m][6] is not None]
        return {"members": members, "name": name, "type": most_frequent([rows[m][4] for m in members]),
                "rate": most_frequent([rows[m][5] for m in members]), "maturity": min(maturities) if maturities else None}

    described = [describe(m) for m in facilities]
    described.sort(key=lambda d: (d["name"], d["type"], d["maturity"] is None, d["maturity"] or date.min, d["members"][0]))
    names = sorted({d["name"] for d in described})

    with conn.transaction():
        for t in CURATED:
            conn.execute(f"DELETE FROM {t}")
        for t, col in SEQUENCES:
            conn.execute("SELECT setval(pg_get_serial_sequence(%s, %s), 1, false)", (t, col))
        borrower_id = {}
        for n in names:
            borrower_id[n] = conn.execute(
                "INSERT INTO canonical_borrowers (canonical_name, period_end_date) VALUES (%s, %s) RETURNING canonical_borrower_id",
                (n, period)).fetchone()[0]
        summary_rows = []
        for d in described:
            d["facility_id"] = conn.execute(
                "INSERT INTO canonical_facilities (canonical_borrower_id, period_end_date, instrument_type_norm, reference_rate, maturity_bucket) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING facility_id",
                (borrower_id[d["name"]], period, d["type"], d["rate"], d["maturity"])).fetchone()[0]
            for m in d["members"]:
                r = rows[m]
                conn.execute("INSERT INTO holding_facility_map (holding_id, facility_id) VALUES (%s, %s)", (m, d["facility_id"]))
                conn.execute(
                    "INSERT INTO facility_comparisons (facility_id, holding_id, period_end_date, bdc_cik, bdc_name, spread_bps_total, "
                    "principal, fair_value_pct_par, excluded_reason, source_url) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (d["facility_id"], m, period, r[1], r[2], r[7], r[8], r[9], r[10], r[11]))
            marks = [rows[m][9] for m in d["members"] if rows[m][9] is not None]
            div = max(marks) - min(marks)
            # exposure_usd (v2 F1): the gap in points applied to the smallest compared position. A ranking key, not a loss estimate.
            smallest = min(rows[m][8] for m in d["members"] if rows[m][9] is not None)
            d.update(lender_count=len(marks), excluded_count=len(d["members"]) - len(marks), divergence=div,
                     flag=flag_for(div, mild, flagged), exposure=exposure_usd(div, smallest))
            conn.execute("INSERT INTO facility_summary (facility_id, lender_count, excluded_count, divergence_pts, divergence_flag, exposure_usd) "
                         "VALUES (%s, %s, %s, %s, %s, %s)", (d["facility_id"], d["lender_count"], d["excluded_count"], div, d["flag"], d["exposure"]))
        for members in collisions:
            cid = conn.execute("INSERT INTO review_clusters (period_end_date, reason) VALUES (%s, 'SAME_BDC_COLLISION') RETURNING cluster_id",
                               (period,)).fetchone()[0]
            for m in members:
                conn.execute("INSERT INTO review_cluster_members (cluster_id, holding_id) VALUES (%s, %s)", (cid, m))

    return {"edges": Counter(e[3] for e in edges), "clusters": len(clusters), "collisions": collisions, "failed": failed,
            "facilities": described, "borrowers": len(names), "skipped": skipped, "log": log, "rows": rows}


def report(conn, res: dict) -> None:
    print(f"AUTO and CONFIRMED pairs used: {sum(res['edges'].values())} ({dict(res['edges'])}); edges skipped: {len(res['skipped'])}")
    print(f"clusters {res['clusters']}: same BDC collision clusters {len(res['collisions'])}, failed the 2-mark test {len(res['failed'])}, "
          f"facilities {len(res['facilities'])}")
    print(f"borrowers {res['borrowers']}")
    reasons = conn.execute("SELECT coalesce(excluded_reason, 'none'), count(*) FROM facility_comparisons WHERE excluded_reason IS NOT NULL "
                           "OR fair_value_pct_par IS NULL GROUP BY 1 ORDER BY 1").fetchall()
    print("excluded holdings in facilities, by reason: " + (", ".join(f"{r} {n}" for r, n in reasons) or "none")
          + f" (total {conn.execute('SELECT coalesce(sum(excluded_count), 0) FROM facility_summary').fetchone()[0]})")
    split = dict(conn.execute("SELECT divergence_flag, count(*) FROM facility_summary GROUP BY 1").fetchall())
    print(f"divergence: AGREEMENT {split.get('AGREEMENT', 0)}, MILD {split.get('MILD', 0)}, FLAGGED {split.get('FLAGGED', 0)}")
    top = conn.execute(
        "SELECT b.canonical_name, f.instrument_type_norm, string_agg(c.bdc_name, ' / ' ORDER BY c.bdc_name), s.divergence_pts, f.facility_id "
        "FROM facility_summary s JOIN canonical_facilities f USING (facility_id) JOIN canonical_borrowers b USING (canonical_borrower_id) "
        "JOIN facility_comparisons c USING (facility_id) WHERE c.fair_value_pct_par IS NOT NULL "
        "GROUP BY b.canonical_name, f.instrument_type_norm, s.divergence_pts, f.facility_id "
        "ORDER BY s.divergence_pts DESC, b.canonical_name, f.facility_id LIMIT 10").fetchall()
    print("10 largest divergences (points of par):")
    for name, typ, bdcs, div, fid in top:
        print(f"  {div:>10.4f}  {name} | {typ} | {bdcs}  (facility {fid})")
    for line in res["log"]:
        print("  log:", line)


PROTECTED = ("label_samples", "labeled_pairs", "candidate_pairs")


def protected_counts(conn) -> dict[str, int]:
    return {t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in PROTECTED}


def main() -> int:
    load_env_file()
    period, cfg = measured_period_end(), load_config()
    t0 = time.perf_counter()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        before = protected_counts(conn)
        print("row counts before: " + ", ".join(f"{t} {n}" for t, n in before.items()))
        res = run(conn, period, cfg)
        seconds = time.perf_counter() - t0
        after = protected_counts(conn)
        print("row counts after:  " + ", ".join(f"{t} {n}" for t, n in after.items()) + ("  (identical)" if before == after else "  (CHANGED)"))
        report(conn, res)
    append_run_time("compare", seconds, period)
    print(f"\ncompare.py wall clock {seconds:.2f}s appended to {RUN_TIMES.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
