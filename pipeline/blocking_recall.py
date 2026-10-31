"""blocking_recall.py: the independent blocking recall check (SPEC 12.5, phase_wise.md 6.9). Report only.

Run: python -m pipeline.blocking_recall --draw | --record <holding_id> <counterpart_id> | --finalize
  --draw      seeded random sample of blocking_recall.sample_size measured-period holdings (seed from config), printed with their
              raw rows and written to docs/blocking_recall_worksheet.md. It lists no counterpart and suggests none: you search the
              other BDCs' schedules by eye, outside the pipeline. Read only.
  --record    stores one hand-found pair in docs/blocking_recall_pending.json (not in the database). A holding with no true
              counterpart gets no entry, so n can be below the sample size.
  --search TEXT --for HOLDING_ID
              read only text search to help the hand check: lists the holdings of the other two BDCs, in the measured period, whose raw
              borrower name contains every word of TEXT (case insensitive). Raw attribute columns only, in holding id order: no score,
              no blocking key, no candidate status, no ranking and no suggestion. It is a plain text search, so a counterpart spelled very
              differently needs another search term from you.
  --finalize  applies the blocking predicate (block.is_candidate, the section 6.2 rule) to each recorded pair and only then writes
              blocking_recall_checks rows with found_by_blocking set. It refuses if rows already exist. Until it runs the table is
              empty, so E9 blockingRecall stays null and no unfinalized pair can reach a metric.
Nothing here writes candidate_pairs, labels or the freeze row, and it never runs block.py, match.py or normalize.py.
"""
from __future__ import annotations

import json
import os
import random
import sys
from datetime import date
from pathlib import Path

import psycopg

from pipeline.block import is_candidate            # the predicate only; importing it runs nothing
from pipeline.config import REPO_ROOT, load_config, load_env_file, measured_period_end

WORKSHEET = REPO_ROOT / "docs" / "blocking_recall_worksheet.md"
PENDING = REPO_ROOT / "docs" / "blocking_recall_pending.json"

DRAW_SQL = ("SELECT holding_id FROM normalized_holdings WHERE period_end_date = %s ORDER BY holding_id")
ROW_SQL = ("SELECT n.holding_id, f.bdc_name, r.portfolio_company_raw, r.instrument_type_raw, r.industry_raw, r.maturity_date_raw, "
           "r.interest_rate_raw, r.principal_raw, r.source_url "
           "FROM normalized_holdings n JOIN raw_holdings r ON r.holding_id = n.holding_id JOIN raw_filings f ON f.filing_id = r.filing_id "
           "WHERE n.holding_id = ANY(%s) ORDER BY n.holding_id")


def draw(conn, period: date, cfg: dict) -> list[int]:
    """The sorted holding ids of the draw. Deterministic: the same seed and the same holdings give the same ids."""
    bl = cfg["blocking_recall"]
    ids = [r[0] for r in conn.execute(DRAW_SQL, (period,)).fetchall()]
    k = min(int(bl["sample_size"]), len(ids))
    return sorted(random.Random(f"{bl['seed']}:blocking_recall").sample(ids, k))


def worksheet_text(conn, ids: list[int], period: date, cfg: dict) -> str:
    bl = cfg["blocking_recall"]
    cols = ["holding_id", "BDC", "Printed name", "Instrument type as printed", "Industry as printed", "Maturity as printed",
            "Interest rate as printed", "Principal as printed", "Source"]
    lines = [f"# Blocking recall worksheet, {period}", "",
             f"{len(ids)} measured-period holdings, drawn at random with seed {bl['seed']} (config blocking_recall), independent of blocking. "
             "Raw attributes only. No counterpart is listed or suggested.", "",
             "For each holding, search the other two BDCs' schedules by eye, outside the pipeline, for the same borrower and the same loan. "
             "Record a pair with `python -m pipeline.blocking_recall --record <holding_id> <counterpart_holding_id>`. "
             "A holding with no true counterpart gets no record. When every holding is done, run `--finalize`.", "",
             "| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for row in conn.execute(ROW_SQL, (ids,)).fetchall():
        lines.append("| " + " | ".join("" if v is None else str(v).replace("|", "/").replace("\n", " ") for v in row) + " |")
    lines += ["", f"Draw: {len(ids)} holdings. Counterparts found by hand: ______ (fill in). Not found: ______."]
    return "\n".join(lines) + "\n"


SEARCH_COLUMNS = ["holding_id", "BDC", "Printed name", "Instrument as printed", "Principal as printed", "Maturity as printed",
                  "Interest rate as printed", "Accession number"]
SEARCH_SQL = ("SELECT n.holding_id, f.bdc_name, r.portfolio_company_raw, r.instrument_type_raw, r.principal_raw, r.maturity_date_raw, "
              "r.interest_rate_raw, f.accession_number "
              "FROM normalized_holdings n JOIN raw_holdings r ON r.holding_id = n.holding_id JOIN raw_filings f ON f.filing_id = r.filing_id "
              "WHERE n.period_end_date = %s AND n.bdc_cik <> %s AND r.portfolio_company_raw ILIKE ALL(%s) ORDER BY n.holding_id")


def search(conn, period: date, holding_id: int, text: str) -> list[tuple]:
    """Holdings of the BDCs other than the one that holds holding_id, in the period, whose raw name contains every word of text."""
    words = text.split()
    if not words:
        raise SystemExit("search refuses: give at least one word.")
    own = conn.execute("SELECT bdc_cik FROM normalized_holdings WHERE holding_id = %s AND period_end_date = %s", (holding_id, period)).fetchone()
    if own is None:
        raise SystemExit(f"search refuses: holding {holding_id} is not in the measured period {period}.")
    patterns = ["%" + w.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%" for w in words]
    return conn.execute(SEARCH_SQL, (period, own[0], patterns)).fetchall()


def search_text(rows: list[tuple]) -> str:
    lines = ["\t".join(SEARCH_COLUMNS)]
    lines += ["\t".join("" if v is None else str(v).replace("\t", " ").replace("\n", " ") for v in row) for row in rows]
    return "\n".join(lines)


def load_pending(path: Path) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else []


def record(conn, period: date, cfg: dict, holding_id: int, counterpart_id: int, path: Path = PENDING) -> None:
    ids = set(draw(conn, period, cfg))
    if holding_id not in ids:
        raise SystemExit(f"record refuses: holding {holding_id} is not in the draw.")
    ends = {r[0]: (r[1], r[2]) for r in conn.execute(
        "SELECT holding_id, bdc_cik, period_end_date FROM normalized_holdings WHERE holding_id = ANY(%s)", ([holding_id, counterpart_id],)).fetchall()}
    if counterpart_id not in ends or holding_id not in ends:
        raise SystemExit("record refuses: unknown holding id.")
    if ends[holding_id][0] == ends[counterpart_id][0]:
        raise SystemExit("record refuses: the counterpart must be in a different BDC.")
    if ends[counterpart_id][1] != period:
        raise SystemExit(f"record refuses: the counterpart is not in the measured period {period}.")
    pending = load_pending(path)
    if any(p["holding_id"] == holding_id for p in pending):
        raise SystemExit(f"record refuses: holding {holding_id} already has a recorded counterpart.")
    pending.append({"holding_id": holding_id, "counterpart_holding_id": counterpart_id})
    path.write_text(json.dumps(pending, indent=1) + "\n", encoding="utf-8")


def finalize(conn, cfg: dict, path: Path = PENDING) -> dict:
    """Apply the blocking predicate to each recorded pair and write blocking_recall_checks. Refuses if rows exist or none is recorded."""
    if conn.execute("SELECT count(*) FROM blocking_recall_checks").fetchone()[0]:
        raise SystemExit("finalize refuses: blocking_recall_checks already has rows.")
    pending = load_pending(path)
    if not pending:
        raise SystemExit("finalize refuses: no pair is recorded.")
    cols = "holding_id, bdc_cik, period_end_date, instrument_type_norm, borrower_normalized, maturity_date, spread_bps"
    out = []
    for p in pending:
        rows = {r[0]: dict(zip(cols.split(", "), r)) for r in conn.execute(
            f"SELECT {cols} FROM normalized_holdings WHERE holding_id = ANY(%s)", ([p["holding_id"], p["counterpart_holding_id"]],)).fetchall()}
        a, b = rows[p["holding_id"]], rows[p["counterpart_holding_id"]]
        found = is_candidate(a, b, cfg)
        shared = conn.execute("SELECT EXISTS (SELECT 1 FROM blocking_keys x JOIN blocking_keys y ON y.block_key = x.block_key "
                              "WHERE x.holding_id = %s AND y.holding_id = %s)", (a["holding_id"], b["holding_id"])).fetchone()[0]
        if found and not shared:
            raise SystemExit(f"finalize refuses: the predicate says candidate but blocking_keys shares no block for {a['holding_id']} and {b['holding_id']}.")
        out.append((a["holding_id"], b["holding_id"], found))
    with conn.transaction():
        for hid, cid, found in out:
            conn.execute("INSERT INTO blocking_recall_checks (holding_id, counterpart_holding_id, found_by_blocking) VALUES (%s, %s, %s)", (hid, cid, found))
    return {"n": len(out), "found": sum(1 for *_, f in out if f)}


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--draw", action="store_true")
    g.add_argument("--record", nargs=2, type=int, metavar=("HOLDING_ID", "COUNTERPART_ID"))
    g.add_argument("--search", metavar="TEXT")
    g.add_argument("--finalize", action="store_true")
    ap.add_argument("--for", dest="for_holding", type=int, metavar="HOLDING_ID", help="with --search: the drawn holding whose counterpart you are looking for")
    args = ap.parse_args(argv)
    if args.search is not None and args.for_holding is None:
        ap.error("--search needs --for HOLDING_ID")
    load_env_file()
    period, cfg = measured_period_end(), load_config()
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        if args.draw:
            ids = draw(conn, period, cfg)
            WORKSHEET.write_text(worksheet_text(conn, ids, period, cfg), encoding="utf-8", newline="\n")
            print(f"drew {len(ids)} holdings for {period}, seed {cfg['blocking_recall']['seed']}; worksheet written to {WORKSHEET.name}")
        elif args.search is not None:
            rows = search(conn, period, args.for_holding, args.search)
            print(search_text(rows))
            print(f"{len(rows)} holdings listed (plain text search)")
        elif args.record:
            record(conn, period, cfg, *args.record)
            print(f"recorded {args.record[0]} with {args.record[1]} (pending until --finalize)")
        else:
            res = finalize(conn, cfg)
            print(f"finalized {res['n']} pairs; {res['found']} were put in one block by blocking")
    return 0


if __name__ == "__main__":
    sys.exit(main())
