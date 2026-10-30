"""The held-out draw (sample_labels.draw_heldout) and SPEC test 25 (a) to (c).

(c) ends with evaluate.py, which is not built yet; it is tested through require_frozen_matching, the check evaluate.py will call.
The pools here are synthetic: pairs with chosen scores, statuses and periods."""
import copy
from datetime import date
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest

from pipeline import config, sample_labels
from pipeline.config import freeze, load_config, matcher_hash, require_frozen_matching
from pipeline.sample_labels import BANDS, draw_heldout, draw_tuning, heldout_frame

from conftest import seed_normalized

CFG = load_config()
P2, P1 = date(2026, 6, 30), date(2026, 3, 31)
CIKS = ["0000000001", "0000000002", "0000000003"]
SCORES = {"AUTO": Decimal("0.95"), "REVIEW": Decimal("0.85"), "JUST_BELOW": Decimal("0.70"), "LOW": Decimal("0.50")}
STATUSES = ["AUTO", "REVIEW", "NO_MATCH", "REJECTED", "CONFIRMED"]      # deliberately unrelated to the band


def pool(conn, sizes: dict[str, int], period: date = P2, tag: str = "p") -> dict[str, list[tuple[int, int]]]:
    """sizes {band: number of candidate pairs}. Each pair is two holdings of different BDCs. Returns the pairs by band."""
    n = sum(sizes.values())
    rows = []
    for i in range(n):
        for c in CIKS[:2]:
            rows.append({"bdc_cik": c, "period_end_date": period, "borrower_normalized": f"{tag}{period:%m}{i}", "instrument_type_norm": "FIRST_LIEN"})
    ids = seed_normalized(conn, rows)
    out, k = {b: [] for b in sizes}, 0
    for band, size in sizes.items():
        for j in range(size):
            a, b = ids[2 * k], ids[2 * k + 1]
            conn.execute("INSERT INTO candidate_pairs (holding_id_a, holding_id_b, score, status) VALUES (%s, %s, %s, %s)",
                         (a, b, SCORES[band] + Decimal(j) / Decimal(100000), STATUSES[k % len(STATUSES)]))
            out[band].append((a, b))
            k += 1
    return out


def frozen(conn):
    freeze(conn, CFG)                                                       # the real repo files and config, as at the freeze


def held(conn):
    return conn.execute("SELECT holding_id_a, holding_id_b, score_band, draw_order FROM label_samples WHERE phase = 'HELDOUT' ORDER BY sample_id").fetchall()


# ------------------------------------------------------------------ SPEC test 25 (a), (b), (c)
def test_25a_the_draw_refuses_with_no_freeze_row(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        pool(conn, {"AUTO": 5})
        with pytest.raises(SystemExit, match="no matcher_freeze row"):
            draw_heldout(conn, P2, CFG)
        assert conn.execute("SELECT count(*) FROM label_samples").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM band_sizes").fetchone()[0] == 0


def make_root(tmp_path: Path) -> Path:
    root = tmp_path / "root"
    (root / "pipeline").mkdir(parents=True)
    for name in ("a", "b"):
        (root / "pipeline" / f"{name}.py").write_text(f"x = '{name}'\n")
    return root


def test_25b_an_edit_to_a_hashed_file_or_config_key_after_the_freeze_refuses_the_draw(migrated_db, tmp_path):
    root = make_root(tmp_path)
    cfg = copy.deepcopy(CFG)
    cfg["freeze"]["hashed_files"] = ["pipeline/a.py", "pipeline/b.py"]
    with psycopg.connect(migrated_db) as conn:
        pool(conn, {"AUTO": 5, "REVIEW": 3})
        freeze(conn, cfg, root)
        f = root / "pipeline/a.py"
        f.write_text(f.read_text() + "y = 1\n")                                              # a hashed source file edited after the freeze
        with pytest.raises(SystemExit, match="matcher changed since the freeze"):
            draw_heldout(conn, P2, cfg, root)
        f.write_text("x = 'a'\n")                                                            # restored: the draw is allowed
        cfg2 = copy.deepcopy(cfg)
        cfg2["bands"]["auto_min"] = 0.91                                                     # a hashed config key
        with pytest.raises(SystemExit, match="matcher changed since the freeze"):
            draw_heldout(conn, P2, cfg2, root)
        cfg3 = copy.deepcopy(cfg)
        cfg3["filers"]["hps"]["unfunded_pattern"] = "x"                                      # filers is hashed too
        with pytest.raises(SystemExit, match="matcher changed"):
            draw_heldout(conn, P2, cfg3, root)
        assert conn.execute("SELECT count(*) FROM label_samples WHERE phase = 'HELDOUT'").fetchone()[0] == 0
        assert draw_heldout(conn, P2, cfg, root)["status"] == "drawn"
        # sampling is not hashed: changing a sample size does not trip the check
        cfg4 = copy.deepcopy(cfg)
        cfg4["sampling"]["heldout_auto"] = 3
        assert draw_heldout(conn, P2, cfg4, root)["status"] == "exists"


def test_25c_an_edit_after_the_draw_makes_the_evaluate_check_refuse(migrated_db, tmp_path):
    root = make_root(tmp_path)
    cfg = copy.deepcopy(CFG)
    cfg["freeze"]["hashed_files"] = ["pipeline/a.py", "pipeline/b.py"]
    with psycopg.connect(migrated_db) as conn:
        pool(conn, {"AUTO": 5})
        freeze(conn, cfg, root)
        draw_heldout(conn, P2, cfg, root)
        stored = conn.execute("SELECT matcher_config_hash FROM band_sizes").fetchone()[0]
        assert stored == conn.execute("SELECT matcher_config_hash FROM matcher_freeze").fetchone()[0] == matcher_hash(cfg, root)     # copied into band_sizes
        assert require_frozen_matching(conn, "evaluate.py", cfg, root) == stored
        (root / "pipeline/b.py").write_text("x = 'changed'\n")
        with pytest.raises(SystemExit, match="matcher changed since the freeze"):
            require_frozen_matching(conn, "evaluate.py", cfg, root)


# ------------------------------------------------------------------ sizes
def test_band_sizes_and_sample_sizes_follow_the_rule_and_small_bands_are_labeled_in_full(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        made = pool(conn, {"AUTO": 100, "REVIEW": 30, "JUST_BELOW": 25, "LOW": 4})
        frozen(conn)
        res = draw_heldout(conn, P2, CFG)
        bs = {r[0]: r[1:] for r in conn.execute("SELECT score_band, band_size, sample_size, matcher_config_hash FROM band_sizes").fetchall()}
        drawn = {b: sum(1 for r in held(conn) if r[2] == b) for b in BANDS}
    assert res["status"] == "drawn" and res["drawn"] == 60 + 25 + 25 + 4
    assert {b: (v[0], v[1]) for b, v in bs.items()} == {"AUTO": (100, 60), "REVIEW": (30, 25), "JUST_BELOW": (25, 25), "LOW": (4, 4)}
    assert drawn == {"AUTO": 60, "REVIEW": 25, "JUST_BELOW": 25, "LOW": 4}
    assert {v[2] for v in bs.values()} == {matcher_hash(CFG)}
    assert sum(len(v) for v in made.values()) == 159                                         # the frame was larger than the sample


def test_the_sampling_numbers_come_from_config():
    s = CFG["sampling"]
    assert (s["heldout_auto"], s["heldout_per_band"], s["heldout_seed"]) == (60, 25, 2)


# ------------------------------------------------------------------ the frame
def test_tuning_pairs_are_never_in_the_frame_and_are_not_counted_in_band_sizes(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        made = pool(conn, {"AUTO": 120, "REVIEW": 6, "JUST_BELOW": 4, "LOW": 3})
        draw_tuning(conn, P2, copy_cfg(tuning_size=40))
        tuning = {(a, b) for a, b in conn.execute("SELECT holding_id_a, holding_id_b FROM label_samples WHERE phase = 'TUNING'").fetchall()}
        assert len(tuning) == 40
        frame = heldout_frame(conn, P2, CFG)
        assert not tuning & {p for ps in frame.values() for p in ps}
        frozen(conn)
        draw_heldout(conn, P2, CFG)
        chosen = {(a, b) for a, b, *_ in held(conn)}
        sizes = dict(conn.execute("SELECT score_band, band_size FROM band_sizes").fetchall())
    assert not tuning & chosen
    in_tuning = {b: sum(1 for p in made[b] if p in tuning) for b in made}
    assert sizes == {b: len(made[b]) - in_tuning[b] for b in made}                           # N_b excludes the tuning pairs
    assert sum(sizes.values()) == 133 - 40


def copy_cfg(**sampling):
    c = copy.deepcopy(CFG)
    c["sampling"].update(sampling)
    return c


def test_band_comes_from_the_stored_score_never_from_the_status(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        made = pool(conn, {"AUTO": 10, "REVIEW": 4, "JUST_BELOW": 3, "LOW": 2})            # statuses cycle AUTO, REVIEW, NO_MATCH, REJECTED, CONFIRMED
        statuses = {s for (s,) in conn.execute("SELECT status FROM candidate_pairs").fetchall()}
        assert statuses == set(STATUSES)
        frame = heldout_frame(conn, P2, CFG)
        assert {b: set(frame[b]) for b in BANDS} == {b: set(made[b]) for b in BANDS}
        # flipping every status changes nothing about the frame
        conn.execute("UPDATE candidate_pairs SET status = 'REJECTED'")
        assert {b: set(heldout_frame(conn, P2, CFG)[b]) for b in BANDS} == {b: set(made[b]) for b in BANDS}
        # a score on an edge: 0.92 is AUTO, 0.80 is REVIEW, 0.65 is JUST_BELOW, just below each falls to the next band
        a, b = made["AUTO"][0]
        for score, band in (("0.92", "AUTO"), ("0.91999999", "REVIEW"), ("0.80", "REVIEW"), ("0.79999999", "JUST_BELOW"), ("0.65", "JUST_BELOW"), ("0.64999999", "LOW")):
            conn.execute("UPDATE candidate_pairs SET score = %s WHERE holding_id_a = %s AND holding_id_b = %s", (Decimal(score), a, b))
            assert (a, b) in heldout_frame(conn, P2, CFG)[band], score


def test_only_measured_period_pairs_are_in_the_frame_and_none_is_drawn_from_another_period(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        now = pool(conn, {"AUTO": 70, "REVIEW": 5}, P2, "m")
        prior = pool(conn, {"AUTO": 40, "REVIEW": 8, "JUST_BELOW": 3}, P1, "q")
        frozen(conn)
        draw_heldout(conn, P2, CFG)
        chosen = {(a, b) for a, b, *_ in held(conn)}
        sizes = dict(conn.execute("SELECT score_band, band_size FROM band_sizes").fetchall())
    assert chosen <= {p for ps in now.values() for p in ps}
    assert not chosen & {p for ps in prior.values() for p in ps}
    assert sizes == {"AUTO": 70, "REVIEW": 5, "JUST_BELOW": 0, "LOW": 0}


# ------------------------------------------------------------------ repeatability, idempotence, redraw
def test_two_draws_are_identical_and_a_rerun_changes_nothing(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        pool(conn, {"AUTO": 90, "REVIEW": 12, "JUST_BELOW": 7, "LOW": 3})
        frozen(conn)
        draw_heldout(conn, P2, CFG)
        first = held(conn)
        stamp = conn.execute("SELECT min(drawn_at), max(drawn_at) FROM label_samples").fetchone()
        assert draw_heldout(conn, P2, CFG)["status"] == "exists"                                # idempotent
        assert held(conn) == first and conn.execute("SELECT min(drawn_at), max(drawn_at) FROM label_samples").fetchone() == stamp
        assert draw_heldout(conn, P2, CFG, redraw=True)["status"] == "drawn"                    # unlabeled: the redraw gives the same draw
        again = held(conn)
    assert again == first                                                                         # same pairs, same bands, same draw order
    assert sorted(r[3] for r in first) == list(range(1, len(first) + 1))                         # draw_order is a permutation of 1 to n
    assert len({r[2] for r in first[:20]}) > 1                                                   # the order mixes the bands


def test_redraw_is_refused_once_a_held_out_label_exists_and_changes_nothing(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        pool(conn, {"AUTO": 70, "REVIEW": 5})
        frozen(conn)
        draw_heldout(conn, P2, CFG)
        sid, a, b = conn.execute("SELECT sample_id, holding_id_a, holding_id_b FROM label_samples WHERE phase = 'HELDOUT' LIMIT 1").fetchone()
        conn.execute("INSERT INTO labeled_pairs (sample_id, holding_id_a, holding_id_b, label, labeled_by, sampling_method) VALUES (%s, %s, %s, 'MATCH', 't', 'STRATIFIED')", (sid, a, b))
        before = (held(conn), conn.execute("SELECT * FROM band_sizes ORDER BY 1").fetchall())
        with pytest.raises(SystemExit, match="already labeled"):
            draw_heldout(conn, P2, CFG, redraw=True)
        assert (held(conn), conn.execute("SELECT * FROM band_sizes ORDER BY 1").fetchall()) == before


def test_the_tuning_draw_is_refused_once_the_held_out_draw_exists(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        pool(conn, {"AUTO": 70, "REVIEW": 5})
        frozen(conn)
        draw_heldout(conn, P2, CFG)
        with pytest.raises(SystemExit, match="band_sizes"):
            draw_tuning(conn, P2, CFG)


def test_the_draw_never_writes_labeled_pairs_or_the_freeze_row(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        pool(conn, {"AUTO": 70, "REVIEW": 5})
        frozen(conn)
        before = (conn.execute("SELECT * FROM matcher_freeze").fetchall(), conn.execute("SELECT count(*) FROM labeled_pairs").fetchone())
        draw_heldout(conn, P2, CFG)
        assert (conn.execute("SELECT * FROM matcher_freeze").fetchall(), conn.execute("SELECT count(*) FROM labeled_pairs").fetchone()) == before
        assert conn.execute("SELECT count(*) FROM candidate_pairs WHERE status NOT IN ('AUTO','REVIEW','NO_MATCH','REJECTED','CONFIRMED')").fetchone()[0] == 0


def test_the_cli_prints_counts_only(migrated_db, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    monkeypatch.setenv("MEASURED_PERIOD_END", "2026-06-30")
    with psycopg.connect(migrated_db) as conn:
        pool(conn, {"AUTO": 70, "REVIEW": 5, "JUST_BELOW": 2, "LOW": 1})
        frozen(conn)
        conn.commit()
    assert sample_labels.main(["--phase", "heldout"]) == 0
    out = capsys.readouterr().out
    assert "drew 68 pairs" in out and "AUTO" in out and "frame   70  drawn  60" in out
    assert len(out.strip().splitlines()) == 5 and "p06" not in out                       # a header and 4 band lines: no pair, holding or name
    assert sample_labels.main(["--phase", "heldout"]) == 0
    assert "already exists: 68 samples" in capsys.readouterr().out
