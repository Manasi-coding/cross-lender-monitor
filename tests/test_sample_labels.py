"""The tuning draw (sample_labels.py --phase tuning) and the read-only tuning report."""
import itertools
from datetime import date
from decimal import Decimal

import psycopg
import pytest

from pipeline import sample_labels, tuning_report
from pipeline.config import load_config

from conftest import seed_normalized

CFG = load_config()
P, OTHER = date(2026, 6, 30), date(2026, 3, 31)
CIKS = ["0000000001", "0000000002", "0000000003"]


def row(cik, name, period=P):
    return {"bdc_cik": cik, "period_end_date": period, "borrower_normalized": name,
            "instrument_type_norm": "FIRST_LIEN", "maturity_date": date(2030, 1, 31), "spread_bps": Decimal(500)}


def seed_pool(conn, n_names=30, with_other_period=True):
    """n_names borrowers each held by 3 BDCs in the measured period: 3 candidate pairs each. Plus pairs in another period."""
    rows = [row(c, f"borrower {i}") for i in range(n_names) for c in CIKS]
    ids = seed_normalized(conn, rows)
    pairs = []
    for i in range(n_names):
        trio = ids[3 * i:3 * i + 3]
        pairs += [(min(a, b), max(a, b)) for a, b in itertools.combinations(trio, 2)]
    other = []
    if with_other_period:
        o = seed_normalized(conn, [row(c, f"later {i}", OTHER) for i in range(5) for c in CIKS[:2]])
        other = [(o[2 * i], o[2 * i + 1]) for i in range(5)]
    scores = [(Decimal("0.5") + Decimal(i % 50) / 100) for i in range(len(pairs) + len(other))]
    for (a, b), s in zip(pairs + other, scores):
        conn.execute("INSERT INTO candidate_pairs (holding_id_a, holding_id_b, score, status) VALUES (%s, %s, %s, %s)",
                     (a, b, s, ["AUTO", "REVIEW", "NO_MATCH", "CONFIRMED"][int(s * 100) % 4]))
    return pairs, other


def samples(conn):
    return conn.execute("SELECT holding_id_a, holding_id_b, draw_order, phase, score_band FROM label_samples ORDER BY draw_order").fetchall()


def test_config_sampling_keys():
    s = CFG["sampling"]
    assert (s["tuning_size"], s["heldout_auto"], s["heldout_per_band"], s["seed"]) == (40, 60, 25, 1)


def test_draw_writes_tuning_size_pairs_with_the_required_columns(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        pairs, _ = seed_pool(conn)
        res = sample_labels.draw_tuning(conn, P, CFG)
        rows = samples(conn)
    assert res["status"] == "drawn" and res["drawn"] == 40 and res["pool"] == len(pairs) == 90
    assert len(rows) == 40
    assert {r[3] for r in rows} == {"TUNING"} and {r[4] for r in rows} == {None}
    assert all(a < b for a, b, *_ in rows)
    assert sorted(r[2] for r in rows) == list(range(1, 41))          # draw_order is a permutation of 1 to 40
    assert len({(a, b) for a, b, *_ in rows}) == 40                    # no duplicates


def test_only_measured_period_pairs_are_drawn_even_when_the_other_period_is_large(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        pairs, other = seed_pool(conn, n_names=4)                      # 12 measured pairs, 5 from another period
        res = sample_labels.draw_tuning(conn, P, CFG)
        rows = {(a, b) for a, b, *_ in samples(conn)}
    assert res["pool"] == 12 and res["drawn"] == 12                    # fewer pairs than tuning_size: all of them
    assert rows == set(pairs) and not rows & set(other)


def test_draw_is_deterministic_for_a_fixed_seed_and_ignores_status_and_score(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        seed_pool(conn)
        sample_labels.draw_tuning(conn, P, CFG)
        first = samples(conn)
        conn.execute("UPDATE candidate_pairs SET score = 1 - score, status = 'REJECTED'")        # the draw may not look at either
        sample_labels.draw_tuning(conn, P, CFG, redraw=True)
        second = samples(conn)
        other_seed = {**CFG, "sampling": {**CFG["sampling"], "seed": 2}}
        sample_labels.draw_tuning(conn, P, other_seed, redraw=True)
        third = samples(conn)
    assert [r[:3] for r in first] == [r[:3] for r in second]
    assert [r[:3] for r in third] != [r[:3] for r in first]            # a different seed gives a different draw


def test_rerun_does_not_redraw_or_duplicate(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        seed_pool(conn)
        sample_labels.draw_tuning(conn, P, CFG)
        before = conn.execute("SELECT sample_id, holding_id_a, holding_id_b, draw_order, drawn_at FROM label_samples ORDER BY 1").fetchall()
        res = sample_labels.draw_tuning(conn, P, CFG)
        after = conn.execute("SELECT sample_id, holding_id_a, holding_id_b, draw_order, drawn_at FROM label_samples ORDER BY 1").fetchall()
    assert res["status"] == "exists" and res["existing"] == 40 and before == after


def test_redraw_replaces_unlabeled_samples_and_refuses_after_a_label(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        seed_pool(conn)
        sample_labels.draw_tuning(conn, P, CFG)
        res = sample_labels.draw_tuning(conn, P, CFG, redraw=True)
        assert res["status"] == "drawn" and res["replaced"] == 40
        sid, a, b = conn.execute("SELECT sample_id, holding_id_a, holding_id_b FROM label_samples LIMIT 1").fetchone()
        conn.execute("INSERT INTO labeled_pairs (sample_id, holding_id_a, holding_id_b, label, labeled_by, sampling_method) "
                     "VALUES (%s, %s, %s, 'MATCH', 'tester', 'BLOCKED')", (sid, a, b))
        with pytest.raises(SystemExit) as err:
            sample_labels.draw_tuning(conn, P, CFG, redraw=True)
        assert "already labeled" in str(err.value) and "1 " in str(err.value)
        assert conn.execute("SELECT count(*) FROM label_samples").fetchone()[0] == 40       # nothing was replaced


def test_draw_refuses_once_the_held_out_sample_exists(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        seed_pool(conn)
        conn.execute("INSERT INTO band_sizes (score_band, band_size, sample_size, matcher_config_hash) VALUES ('AUTO', 10, 5, 'h')")
        with pytest.raises(SystemExit) as err:
            sample_labels.draw_tuning(conn, P, CFG)
        assert "band_sizes" in str(err.value)


def test_heldout_phase_says_it_is_built_on_day_8(capsys):
    assert sample_labels.main(["--phase", "heldout"]) == 2
    assert "Day 8" in capsys.readouterr().out


def test_tuning_report_counts_and_lists_auto_pairs_and_changes_nothing(migrated_db, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    with psycopg.connect(migrated_db) as conn:
        pairs, _ = seed_pool(conn, n_names=3, with_other_period=False)
        sample_labels.draw_tuning(conn, P, CFG)
        conn.execute("UPDATE candidate_pairs SET status = 'AUTO'")
        sids = conn.execute("SELECT sample_id, holding_id_a, holding_id_b FROM label_samples ORDER BY sample_id").fetchall()
        for (sid, a, b), label in zip(sids, ["MATCH", "NO_MATCH", "UNSURE"] + ["MATCH"] * 6):
            conn.execute("INSERT INTO labeled_pairs (sample_id, holding_id_a, holding_id_b, label, labeled_by, sampling_method) "
                         "VALUES (%s, %s, %s, %s, 't', 'BLOCKED')", (sid, a, b, label))
        conn.commit()
        snapshot = [conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("label_samples", "labeled_pairs", "candidate_pairs", "normalized_holdings")]
    assert tuning_report.main([]) == 0
    out = capsys.readouterr().out
    assert "tuning samples drawn 9, labeled 9, unlabeled 0" in out
    assert "MATCH 7, NO_MATCH 1, UNSURE 1 (total 9)" in out
    assert "AUTO pairs labeled NO_MATCH or UNSURE: 2" in out
    with psycopg.connect(migrated_db) as conn:
        assert snapshot == [conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in ("label_samples", "labeled_pairs", "candidate_pairs", "normalized_holdings")]
