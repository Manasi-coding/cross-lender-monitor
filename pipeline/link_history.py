"""link_history.py: the within-BDC history link and the persistence label (F3, SPEC 12.11). Report only.

Run: python -m pipeline.link_history            full rebuild of holding_history_links and history_build
     python -m pipeline.link_history --worksheet  30 random links with raw attributes for the hand check (writes a markdown file)
     python -m pipeline.link_history --record <holding_id> <prior_holding_id> <MATCH|NO_MATCH|UNSURE> --by <name>
Reads only normalized_holdings (and raw_holdings for the worksheet). It never reads candidate_pairs, labels or matcher output, and never
runs normalize.py, block.py or match.py. The prior quarter is history: no candidate pair, facility or label sample comes from it.

Link rule. Key (bdc_cik, borrower_normalized, instrument_type_norm). If exactly one current and one prior holding share the key they
link (EXACT_KEY). If several share the key, a pair links only when the maturity dates are equal and exactly one current and one prior
holding share the key and that maturity (EXACT_MATURITY). When both holdings have a principal currency it must be equal, otherwise the
pair stays unlinked and is counted. Anything else stays unlinked and is counted, never guessed. A prior holding links to at most one
current holding.
"""
from __future__ import annotations

import os
import random
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg

from pipeline.config import REPO_ROOT, load_config, load_env_file, measured_period_end

WORKSHEET = REPO_ROOT / "docs" / "history_link_worksheet.md"

LINK_SQL = """
WITH cur AS (SELECT holding_id, bdc_cik, borrower_normalized, instrument_type_norm, maturity_date, principal_currency
               FROM normalized_holdings WHERE period_end_date = %(period)s AND borrower_normalized IS NOT NULL),
     pri AS (SELECT holding_id, bdc_cik, borrower_normalized, instrument_type_norm, maturity_date, principal_currency
               FROM normalized_holdings WHERE period_end_date = %(prior)s AND borrower_normalized IS NOT NULL),
     key_c AS (SELECT bdc_cik, borrower_normalized, instrument_type_norm, count(*) n FROM cur GROUP BY 1, 2, 3),
     key_p AS (SELECT bdc_cik, borrower_normalized, instrument_type_norm, count(*) n FROM pri GROUP BY 1, 2, 3),
     mat_c AS (SELECT bdc_cik, borrower_normalized, instrument_type_norm, maturity_date, count(*) n FROM cur WHERE maturity_date IS NOT NULL GROUP BY 1, 2, 3, 4),
     mat_p AS (SELECT bdc_cik, borrower_normalized, instrument_type_norm, maturity_date, count(*) n FROM pri WHERE maturity_date IS NOT NULL GROUP BY 1, 2, 3, 4),
     by_key AS (
       SELECT c.holding_id AS holding_id, p.holding_id AS prior_holding_id, 'EXACT_KEY' AS link_rule, c.principal_currency AS cc, p.principal_currency AS pc
         FROM cur c JOIN pri p USING (bdc_cik, borrower_normalized, instrument_type_norm)
         JOIN key_c kc USING (bdc_cik, borrower_normalized, instrument_type_norm)
         JOIN key_p kp USING (bdc_cik, borrower_normalized, instrument_type_norm)
        WHERE kc.n = 1 AND kp.n = 1),
     by_maturity AS (
       SELECT c.holding_id, p.holding_id AS prior_holding_id, 'EXACT_MATURITY' AS link_rule, c.principal_currency AS cc, p.principal_currency AS pc
         FROM cur c JOIN pri p ON p.bdc_cik = c.bdc_cik AND p.borrower_normalized = c.borrower_normalized
                              AND p.instrument_type_norm = c.instrument_type_norm AND p.maturity_date = c.maturity_date
         JOIN key_c kc ON (kc.bdc_cik, kc.borrower_normalized, kc.instrument_type_norm) = (c.bdc_cik, c.borrower_normalized, c.instrument_type_norm)
         JOIN key_p kp ON (kp.bdc_cik, kp.borrower_normalized, kp.instrument_type_norm) = (c.bdc_cik, c.borrower_normalized, c.instrument_type_norm)
         JOIN mat_c mc ON (mc.bdc_cik, mc.borrower_normalized, mc.instrument_type_norm, mc.maturity_date) = (c.bdc_cik, c.borrower_normalized, c.instrument_type_norm, c.maturity_date)
         JOIN mat_p mp ON (mp.bdc_cik, mp.borrower_normalized, mp.instrument_type_norm, mp.maturity_date) = (c.bdc_cik, c.borrower_normalized, c.instrument_type_norm, c.maturity_date)
        WHERE NOT (kc.n = 1 AND kp.n = 1) AND mc.n = 1 AND mp.n = 1),
     cand AS (SELECT * FROM by_key UNION ALL SELECT * FROM by_maturity)
SELECT holding_id, prior_holding_id, link_rule, (cc IS NOT NULL AND pc IS NOT NULL AND cc <> pc) AS currency_mismatch FROM cand ORDER BY holding_id
"""


def prior_period(conn, period: date) -> date | None:
    """The latest normalized quarter before the measured one: the history quarter."""
    return conn.execute("SELECT max(period_end_date) FROM normalized_holdings WHERE period_end_date < %s", (period,)).fetchone()[0]


def run(conn, period: date) -> dict:
    """Full rebuild of holding_history_links and history_build in one transaction. Returns counts."""
    prior = prior_period(conn, period)
    if prior is None:
        raise SystemExit("link_history refuses: no normalized quarter before the measured one.")
    cand = conn.execute(LINK_SQL, {"period": period, "prior": prior}).fetchall()
    links = [(h, p, rule) for h, p, rule, bad in cand if not bad]
    mismatched = sum(1 for *_, bad in cand if bad)
    current = conn.execute("SELECT count(*) FROM normalized_holdings WHERE period_end_date = %s", (period,)).fetchone()[0]
    with conn.transaction():
        conn.execute("DELETE FROM holding_history_links")
        with conn.cursor() as cur:
            cur.executemany("INSERT INTO holding_history_links (holding_id, prior_holding_id, link_rule) VALUES (%s, %s, %s)", links)
        conn.execute("DELETE FROM history_build")
        conn.execute("INSERT INTO history_build (build_id, prior_period_end, period_end_date, current_holdings, linked) VALUES (1, %s, %s, %s, %s)",
                     (prior, period, current, len(links)))
    by_rule = {r: sum(1 for *_, x in links if x == r) for r in ("EXACT_KEY", "EXACT_MATURITY")}
    per_bdc = conn.execute(
        "SELECT n.bdc_cik, count(*) AS holdings, count(l.holding_id) AS linked FROM normalized_holdings n "
        "LEFT JOIN holding_history_links l ON l.holding_id = n.holding_id WHERE n.period_end_date = %s GROUP BY 1 ORDER BY 1", (period,)).fetchall()
    return {"prior": prior, "current": current, "linked": len(links), "currency_mismatch": mismatched, "by_rule": by_rule,
            "unlinked": current - len(links), "per_bdc": per_bdc}


# ------------------------------------------------------------------ persistence, a pure function (SPEC 12.11)
def persistence(current_flag: str, current_pts: Decimal, prior_flag: str, prior_pts: Decimal, dead_band: Decimal) -> str:
    """CLOSED (current AGREEMENT, prior not), then WIDENED (delta at or above the dead band), NARROWED (at or below minus it), else STABLE.
    NO_PRIOR (fewer than 2 prior marks) is decided by the caller, which has no prior divergence to pass."""
    if current_flag == "AGREEMENT" and prior_flag != "AGREEMENT":
        return "CLOSED"
    delta = current_pts - prior_pts
    if delta >= dead_band:
        return "WIDENED"
    if delta <= -dead_band:
        return "NARROWED"
    return "STABLE"


# ------------------------------------------------------------------ the hand check
def worksheet_text(conn, cfg: dict) -> str:
    seed = cfg["evidence"]["history_check_seed"]
    size = int(cfg["evidence"]["history_check_size"])
    ids = [r[0] for r in conn.execute("SELECT holding_id FROM holding_history_links ORDER BY holding_id").fetchall()]
    pick = sorted(random.Random(f"{seed}:history_check").sample(ids, min(size, len(ids))))
    sql = ("SELECT l.holding_id, l.prior_holding_id, l.link_rule, f.bdc_name, rc.portfolio_company_raw, rp.portfolio_company_raw, "
           "rc.instrument_type_raw, rp.instrument_type_raw, rc.maturity_date_raw, rp.maturity_date_raw, rc.interest_rate_raw, rp.interest_rate_raw, "
           "rc.source_url, rp.source_url FROM holding_history_links l JOIN raw_holdings rc ON rc.holding_id = l.holding_id "
           "JOIN raw_holdings rp ON rp.holding_id = l.prior_holding_id JOIN raw_filings f ON f.filing_id = rc.filing_id "
           "WHERE l.holding_id = ANY(%s) ORDER BY l.holding_id")
    cols = ["holding_id", "prior_holding_id", "rule", "BDC", "Name now", "Name before", "Type now", "Type before", "Maturity now",
            "Maturity before", "Rate now", "Rate before", "Source now", "Source before"]
    lines = [f"# History link worksheet", "",
             f"{len(pick)} links drawn at random with seed {seed} (config evidence). Raw attributes only. For each row decide whether the two holdings are "
             "the same position in the same BDC one quarter apart, from the filings. Record with "
             "`python -m pipeline.link_history --record <holding_id> <prior_holding_id> <MATCH|NO_MATCH|UNSURE> --by <name>`.", "",
             "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in conn.execute(sql, (pick,)).fetchall():
        lines.append("| " + " | ".join("" if v is None else str(v).replace("|", "/").replace("\n", " ") for v in row) + " |")
    return "\n".join(lines) + "\n"


def record(conn, holding_id: int, prior_id: int, label: str, by: str) -> None:
    if label not in ("MATCH", "NO_MATCH", "UNSURE"):
        raise SystemExit("record refuses: label must be MATCH, NO_MATCH or UNSURE.")
    if not by.strip():
        raise SystemExit("record refuses: --by is required.")
    if not conn.execute("SELECT 1 FROM holding_history_links WHERE holding_id = %s AND prior_holding_id = %s", (holding_id, prior_id)).fetchone():
        raise SystemExit("record refuses: that pair is not a stored link.")
    conn.execute("INSERT INTO history_link_checks (holding_id, prior_holding_id, label, labeled_by) VALUES (%s, %s, %s, %s) "
                 "ON CONFLICT (holding_id, prior_holding_id) DO UPDATE SET label = EXCLUDED.label, labeled_by = EXCLUDED.labeled_by, checked_at = now()",
                 (holding_id, prior_id, label, by.strip()))


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--worksheet", action="store_true")
    ap.add_argument("--record", nargs=3, metavar=("HOLDING_ID", "PRIOR_ID", "LABEL"))
    ap.add_argument("--by")
    args = ap.parse_args(argv)
    load_env_file()
    period, cfg = measured_period_end(), load_config()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        if args.worksheet:
            WORKSHEET.write_text(worksheet_text(conn, cfg), encoding="utf-8", newline="\n")
            print(f"worksheet written to {WORKSHEET.name}")
        elif args.record:
            record(conn, int(args.record[0]), int(args.record[1]), args.record[2], args.by or "")
            print("recorded")
        else:
            res = run(conn, period)
            print(f"history link, {res['prior']} to {period}: {res['linked']} of {res['current']} holdings linked "
                  f"(EXACT_KEY {res['by_rule']['EXACT_KEY']}, EXACT_MATURITY {res['by_rule']['EXACT_MATURITY']}); "
                  f"unlinked {res['unlinked']}, of which {res['currency_mismatch']} candidate links dropped for a currency mismatch")
            for cik, n, k in res["per_bdc"]:
                print(f"  {cik}: {k} of {n} linked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
