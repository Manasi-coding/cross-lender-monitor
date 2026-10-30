"""The out-of-time draw (sample_labels.draw_outoftime): a sample of the prior quarter, drawn after the freeze.
The pools are synthetic: pairs with chosen scores, statuses and periods."""
import copy
from datetime import date

import psycopg
import pytest

from pipeline import config, sample_labels
from pipeline.config import freeze, load_config, unfreeze
from pipeline.sample_labels import BANDS, draw_heldout, draw_outoftime

from conftest import seed_normalized
from test_heldout import P1, P2, pool, frozen, held

CFG = load_config()


def oot(conn):
    return conn.execute("SELECT holding_id_a, holding_id_b, score_band, draw_order FROM label_samples WHERE phase = 'OUTOFTIME' ORDER BY sample_id").fetchall()


def test_the_config_numbers():
    s = CFG["sampling"]
    assert (s["outoftime_period"], s["outoftime_seed"], s["outoftime_sizes"]) == ("2026-03-31", 3, {"AUTO": 30, "REVIEW": 25, "JUST_BELOW": 25, "LOW": 0})
    assert s["outoftime_seed"] != s["heldout_seed"] != s["seed"]


def test_sizes_follow_the_caps_small_bands_in_full_and_low_not_sampled(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        pool(conn, {"AUTO": 100, "REVIEW": 5, "JUST_BELOW": 7, "LOW": 13}, P1, "q")
        frozen(conn)
        res = draw_outoftime(conn, P2, CFG)
        rows = {r[0]: r[1:] for r in conn.execute("SELECT score_band, band_size, sample_size, period_end_date, draw_seed, matcher_config_hash FROM outoftime_band_sizes").fetchall()}
        drawn = {b: sum(1 for r in oot(conn) if r[2] == b) for b in BANDS}
        stored = conn.execute("SELECT matcher_config_hash FROM matcher_freeze").fetchone()[0]
    assert res["status"] == "drawn" and res["drawn"] == 30 + 5 + 7
    assert {b: v[:2] for b, v in rows.items()} == {"AUTO": (100, 30), "REVIEW": (5, 5), "JUST_BELOW": (7, 7), "LOW": (13, 0)}
    assert drawn == {"AUTO": 30, "REVIEW": 5, "JUST_BELOW": 7, "LOW": 0}
    assert {(v[2], v[3], v[4]) for v in rows.values()} == {(P1, 3, stored)}


def test_band_comes_from_the_stored_score_never_from_the_status(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        made = pool(conn, {"AUTO": 40, "REVIEW": 4, "JUST_BELOW": 3, "LOW": 2}, P1, "q")        # statuses cycle through all five values
        frozen(conn)
        draw_outoftime(conn, P2, CFG)
        by_band = {b: {(a, c) for a, c, band, _ in oot(conn) if band == b} for b in BANDS}
    assert by_band["REVIEW"] == set(made["REVIEW"]) and by_band["JUST_BELOW"] == set(made["JUST_BELOW"])
    assert by_band["AUTO"] <= set(made["AUTO"]) and len(by_band["AUTO"]) == 30 and not by_band["LOW"]


def test_only_prior_quarter_pairs_are_drawn_and_held_out_has_no_prior_quarter_pair(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        now = pool(conn, {"AUTO": 70, "REVIEW": 5}, P2, "m")
        prior = pool(conn, {"AUTO": 40, "REVIEW": 8, "JUST_BELOW": 3}, P1, "q")
        frozen(conn)
        draw_heldout(conn, P2, CFG)
        draw_outoftime(conn, P2, CFG)
        h = {(a, b) for a, b, *_ in held(conn)}
        o = {(a, b) for a, b, *_ in oot(conn)}
        sizes = dict(conn.execute("SELECT score_band, band_size FROM outoftime_band_sizes").fetchall())
    now_pairs, prior_pairs = {p for v in now.values() for p in v}, {p for v in prior.values() for p in v}
    assert o <= prior_pairs and not o & now_pairs
    assert h <= now_pairs and not h & prior_pairs
    assert sizes == {"AUTO": 40, "REVIEW": 8, "JUST_BELOW": 3, "LOW": 0}
    assert len(o) == 30 + 8 + 3


def test_two_draws_are_identical_a_rerun_changes_nothing_and_the_seed_matters(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        pool(conn, {"AUTO": 90, "REVIEW": 12, "JUST_BELOW": 7, "LOW": 3}, P1, "q")
        frozen(conn)
        draw_outoftime(conn, P2, CFG)
        first = oot(conn)
        stamp = conn.execute("SELECT min(drawn_at), max(drawn_at) FROM label_samples").fetchone()
        assert draw_outoftime(conn, P2, CFG)["status"] == "exists"
        assert oot(conn) == first and conn.execute("SELECT min(drawn_at), max(drawn_at) FROM label_samples").fetchone() == stamp
        assert draw_outoftime(conn, P2, CFG, redraw=True)["status"] == "drawn"
        assert oot(conn) == first
        other = copy.deepcopy(CFG)
        other["sampling"]["outoftime_seed"] = 4
        draw_outoftime(conn, P2, other, redraw=True)
        assert oot(conn) != first
    assert sorted(r[3] for r in first) == list(range(1, len(first) + 1))


def test_refuses_with_no_freeze_row_and_after_a_hashed_edit(migrated_db, tmp_path):
    with psycopg.connect(migrated_db) as conn:
        pool(conn, {"AUTO": 5}, P1, "q")
        with pytest.raises(SystemExit, match="no matcher_freeze row"):
            draw_outoftime(conn, P2, CFG)
        root = tmp_path / "root"
        (root / "pipeline").mkdir(parents=True)
        (root / "pipeline" / "a.py").write_text("x = 1\n")
        cfg = copy.deepcopy(CFG)
        cfg["freeze"]["hashed_files"] = ["pipeline/a.py"]
        freeze(conn, cfg, root)
        (root / "pipeline" / "a.py").write_text("x = 2\n")
        with pytest.raises(SystemExit, match="matcher changed since the freeze"):
            draw_outoftime(conn, P2, cfg, root)
        cfg2 = copy.deepcopy(cfg)
        cfg2["bands"]["auto_min"] = 0.91
        with pytest.raises(SystemExit, match="matcher changed"):
            draw_outoftime(conn, P2, cfg2, root)
        assert conn.execute("SELECT count(*) FROM label_samples").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM outoftime_band_sizes").fetchone()[0] == 0


def test_refuses_when_the_period_is_the_measured_period(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        pool(conn, {"AUTO": 5}, P2, "m")
        frozen(conn)
        cfg = copy.deepcopy(CFG)
        cfg["sampling"]["outoftime_period"] = "2026-06-30"
        with pytest.raises(SystemExit, match="is the measured period"):
            draw_outoftime(conn, P2, cfg)
        assert conn.execute("SELECT count(*) FROM label_samples").fetchone()[0] == 0


def test_redraw_is_refused_once_an_out_of_time_label_exists(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        pool(conn, {"AUTO": 40, "REVIEW": 5}, P1, "q")
        frozen(conn)
        draw_outoftime(conn, P2, CFG)
        sid, a, b = conn.execute("SELECT sample_id, holding_id_a, holding_id_b FROM label_samples WHERE phase = 'OUTOFTIME' LIMIT 1").fetchone()
        conn.execute("INSERT INTO labeled_pairs (sample_id, holding_id_a, holding_id_b, label, labeled_by, sampling_method) VALUES (%s, %s, %s, 'MATCH', 't', 'STRATIFIED')", (sid, a, b))
        before = (oot(conn), conn.execute("SELECT * FROM outoftime_band_sizes ORDER BY 1").fetchall())
        with pytest.raises(SystemExit, match="already labeled"):
            draw_outoftime(conn, P2, CFG, redraw=True)
        assert (oot(conn), conn.execute("SELECT * FROM outoftime_band_sizes ORDER BY 1").fetchall()) == before


def test_the_held_out_draw_stores_its_seed_and_the_draws_never_write_labels_or_the_freeze(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        pool(conn, {"AUTO": 70, "REVIEW": 5}, P2, "m")
        pool(conn, {"AUTO": 40}, P1, "q")
        frozen(conn)
        before = (conn.execute("SELECT * FROM matcher_freeze").fetchall(), conn.execute("SELECT count(*) FROM labeled_pairs").fetchone())
        draw_heldout(conn, P2, CFG)
        draw_outoftime(conn, P2, CFG)
        assert {r[0] for r in conn.execute("SELECT draw_seed FROM band_sizes").fetchall()} == {2}
        assert (conn.execute("SELECT * FROM matcher_freeze").fetchall(), conn.execute("SELECT count(*) FROM labeled_pairs").fetchone()) == before


def test_the_cli_prints_counts_only(migrated_db, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("MEASURED_PERIOD_END", "2026-06-30")
    with psycopg.connect(migrated_db) as conn:
        pool(conn, {"AUTO": 50, "REVIEW": 5, "JUST_BELOW": 2, "LOW": 1}, P1, "q")
        frozen(conn)
        conn.commit()
    assert sample_labels.main(["--phase", "outoftime"]) == 0
    out = capsys.readouterr().out
    assert "drew 37 pairs" in out and "seed 3" in out and "frame   50  drawn  30" in out and "frame    1  drawn   0" in out
    assert len(out.strip().splitlines()) == 5 and "q03" not in out
    assert sample_labels.main(["--phase", "outoftime"]) == 0
    assert "already exists: 37 samples" in capsys.readouterr().out


def test_unfreeze_removes_out_of_time_artifacts_and_keeps_tuning(migrated_db, tmp_path):
    with psycopg.connect(migrated_db) as conn:
        a, b, c, d = seed_normalized(conn, [
            {"bdc_cik": "0000000001", "period_end_date": P2, "borrower_normalized": "x", "instrument_type_norm": "FIRST_LIEN"},
            {"bdc_cik": "0000000002", "period_end_date": P2, "borrower_normalized": "x", "instrument_type_norm": "FIRST_LIEN"},
            {"bdc_cik": "0000000001", "period_end_date": P1, "borrower_normalized": "y", "instrument_type_norm": "FIRST_LIEN"},
            {"bdc_cik": "0000000002", "period_end_date": P1, "borrower_normalized": "y", "instrument_type_norm": "FIRST_LIEN"}])
        ids = {}
        for phase, (x, y), band, method in (("TUNING", (a, b), None, "BLOCKED"), ("OUTOFTIME", (c, d), "AUTO", "STRATIFIED")):
            sid = conn.execute("INSERT INTO label_samples (holding_id_a, holding_id_b, phase, score_band, draw_order) VALUES (%s, %s, %s, %s, 1) RETURNING sample_id",
                               (x, y, phase, band)).fetchone()[0]
            conn.execute("INSERT INTO labeled_pairs (sample_id, holding_id_a, holding_id_b, label, labeled_by, sampling_method, score_band) VALUES (%s, %s, %s, 'MATCH', 't', %s, %s)",
                         (sid, x, y, method, band))
            ids[phase] = sid
        conn.execute("INSERT INTO outoftime_band_sizes (score_band, band_size, sample_size, period_end_date, draw_seed, matcher_config_hash) VALUES ('AUTO', 9, 1, %s, 3, 'h')", (P1,))
        conn.execute("INSERT INTO matcher_freeze (matcher_config_hash) VALUES ('h')")
        conn.commit()
        res = unfreeze(conn, tmp_path / "backups", confirmed=True)
        assert conn.execute("SELECT sample_id, phase FROM label_samples").fetchall() == [(ids["TUNING"], "TUNING")]
        assert conn.execute("SELECT sampling_method FROM labeled_pairs").fetchall() == [("BLOCKED",)]
        assert conn.execute("SELECT count(*) FROM outoftime_band_sizes").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM matcher_freeze").fetchone()[0] == 0
    import json
    from pathlib import Path
    dump = json.loads(Path(res["backup"]).read_text())
    assert (len(dump["label_samples_outoftime"]), len(dump["labeled_pairs_outoftime"]), len(dump["outoftime_band_sizes"])) == (1, 1, 1)
