"""report.py sections added with the Day 9 core: machine spec, run-time medians and blocking efficiency (SPEC 12.9)."""
import json
from datetime import date

import psycopg

from pipeline import report

P2 = date(2026, 6, 30)


def test_machine_section_names_every_item():
    text = report.section_machine()
    for item in ("OS", "CPU", "Logical CPUs", "RAM", "Python", "Node", "Docker"):
        assert f"| {item} |" in text


def test_run_time_median_uses_the_last_three_runs_of_the_period(tmp_path, monkeypatch):
    f = tmp_path / "rt.jsonl"
    lines = [{"module": "block", "seconds": s, "period": "2026-06-30", "recorded_at": f"2026-10-30T12:0{i}:00+00:00"} for i, s in enumerate([9.0, 1.0, 3.0, 2.0])]
    lines.append({"module": "block", "seconds": 100.0, "period": "2026-03-31", "recorded_at": "2026-10-30T13:00:00+00:00"})
    f.write_text("\n".join(json.dumps(l) for l in lines) + "\n")
    monkeypatch.setattr(report, "RUN_TIMES", f)
    text = report.section_run_times(P2)
    assert "| block | 3 | 2.000 | 1.000, 3.000, 2.000 |" in text                 # median of 1, 3, 2; the old 9.0 and the other period are out
    assert "| match |" not in text and "| compare |" not in text


def test_blocking_section_shows_all_pairs_from_counts_and_not_yet_measured(migrated_db):
    from conftest import seed_normalized
    with psycopg.connect(migrated_db) as conn:
        rows = [{"bdc_cik": c, "period_end_date": P2, "borrower_normalized": f"b{c}{i}", "instrument_type_norm": "FIRST_LIEN"}
                for c, n in (("0000000001", 3), ("0000000002", 2), ("0000000003", 4)) for i in range(n)]
        seed_normalized(conn, rows)
        text = report.section_blocking(conn, P2)
    assert "| all_pairs | 26 |" in text                                              # 3*2 + 3*4 + 2*4
    assert "Not yet measured" in text
