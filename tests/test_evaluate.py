"""evaluate.py: refusals (SPEC test 25c), the two precision numbers, Wilson values, separation of the phases.
The pools are synthetic: pairs with chosen scores and statuses, labeled here with chosen labels."""
import copy
from decimal import Decimal

import psycopg
import pytest

from pipeline import evaluate
from pipeline.config import freeze, load_config
from pipeline.evaluate import build_report, render, two_numbers, wilson
from pipeline.sample_labels import draw_heldout, draw_outoftime

from conftest import seed_normalized
from test_heldout import P1, P2, frozen, make_root, pool

CFG = load_config()
Z = Decimal("1.96")


def label(conn, phase: str, plan: dict[str, list[str]]):
    """plan {band: [labels]}: the labels go to that band's samples of the phase, in sample_id order."""
    for band, labels in plan.items():
        sids = conn.execute("SELECT sample_id, holding_id_a, holding_id_b FROM label_samples WHERE phase = %s AND score_band = %s ORDER BY sample_id",
                            (phase, band)).fetchall()
        assert len(sids) == len(labels), (phase, band, len(sids), len(labels))
        for (sid, a, b), lab in zip(sids, labels):
            conn.execute("INSERT INTO labeled_pairs (sample_id, holding_id_a, holding_id_b, label, labeled_by, sampling_method, score_band) "
                         "VALUES (%s, %s, %s, %s, 't', %s, %s)", (sid, a, b, lab, "BLOCKED" if phase == "TUNING" else "STRATIFIED", band))


HELD = {"AUTO": ["MATCH"] * 55 + ["NO_MATCH"] * 3 + ["UNSURE"] * 2,
        "REVIEW": ["MATCH"] * 3 + ["NO_MATCH"] + ["UNSURE"],
        "JUST_BELOW": ["MATCH", "NO_MATCH", "UNSURE"],
        "LOW": ["NO_MATCH", "NO_MATCH"]}


def scenario(conn, with_oot=True):
    pool(conn, {"AUTO": 100, "REVIEW": 5, "JUST_BELOW": 3, "LOW": 2}, P2, "m")
    if with_oot:
        pool(conn, {"AUTO": 40, "REVIEW": 2, "JUST_BELOW": 2, "LOW": 3}, P1, "q")
    frozen(conn)
    draw_heldout(conn, P2, CFG)
    if with_oot:
        draw_outoftime(conn, P2, CFG)
    label(conn, "HELDOUT", HELD)


# ------------------------------------------------------------------ Wilson, hand computed (z = 1.96)
def test_wilson_matches_hand_computed_values():
    for (k, n), (lo, hi) in {(60, 60): ("0.9398", "1.0000"), (58, 60): ("0.8864", "0.9908"), (30, 60): ("0.3773", "0.6227")}.items():
        p, low, high = wilson(k, n, Z)
        assert p == Decimal(k) / Decimal(n)
        assert (low.quantize(Decimal("0.0001")), high.quantize(Decimal("0.0001"))) == (Decimal(lo), Decimal(hi)), (k, n)
    p, low, high = wilson(0, 60, Z)
    assert low == 0 and high.quantize(Decimal("0.0001")) == Decimal("0.0602")
    assert wilson(0, 0, Z) is None                                            # no division by zero


def test_wilson_stays_inside_zero_and_one_and_z_comes_from_config():
    assert Decimal(CFG["evaluation"]["wilson_z"]) == Z
    for k, n in ((0, 1), (1, 1), (60, 60), (0, 7)):
        _, lo, hi = wilson(k, n, Z)
        assert 0 <= lo <= hi <= 1


# ------------------------------------------------------------------ the two numbers
def test_unsure_is_excluded_in_one_number_and_counted_wrong_in_the_other():
    r = two_numbers({"MATCH": 55, "NO_MATCH": 3, "UNSURE": 2}, Z)
    assert (r["excluded"]["k"], r["excluded"]["n"]) == (55, 58)
    assert (r["worst_case"]["k"], r["worst_case"]["n"]) == (55, 60)
    assert r["excluded"]["ci"][0] == Decimal(55) / Decimal(58) and r["worst_case"]["ci"][0] == Decimal(55) / Decimal(60)
    assert r["worst_case"]["ci"][1] < r["excluded"]["ci"][1]                    # the worst case is never above
    assert two_numbers({"MATCH": 0, "NO_MATCH": 0, "UNSURE": 0}, Z)["excluded"]["ci"] is None
    assert two_numbers({"MATCH": 0, "NO_MATCH": 0, "UNSURE": 4}, Z)["excluded"]["ci"] is None       # all UNSURE: excluded is 0 of 0
    assert two_numbers({"MATCH": 0, "NO_MATCH": 0, "UNSURE": 4}, Z)["worst_case"]["ci"][0] == 0


def test_the_report_counts_per_band_and_gives_both_numbers_for_the_sampled_band(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        scenario(conn)
        rep = build_report(conn, CFG)
    b = rep["heldout"]["bands"]
    assert {k: (v["frame"], v["sampled"], v["full"]) for k, v in b.items()} == {
        "AUTO": (100, 60, False), "REVIEW": (5, 5, True), "JUST_BELOW": (3, 3, True), "LOW": (2, 2, True)}
    assert b["AUTO"]["counts"] == {"MATCH": 55, "NO_MATCH": 3, "UNSURE": 2}
    assert (b["AUTO"]["excluded"]["k"], b["AUTO"]["excluded"]["n"], b["AUTO"]["worst_case"]["n"]) == (55, 58, 60)
    for full in ("REVIEW", "JUST_BELOW", "LOW"):                              # labeled in full: counts, no estimate
        assert "excluded" not in b[full] and "worst_case" not in b[full]
    assert b["REVIEW"]["counts"] == {"MATCH": 3, "NO_MATCH": 1, "UNSURE": 1}
    text = render(rep)
    assert "AUTO: sampled 60 of 100. precision" in text
    assert "UNSURE excluded: 55 of 58 = 94.8%" in text and "worst case, UNSURE counted as wrong: 55 of 60 = 91.7%" in text
    assert "REVIEW: labeled in full, 5 of 5. Counts, not an estimate. MATCH 3 of 5" in text
    assert "match rate (matches the matcher missed" not in text or "JUST_BELOW: labeled in full" in text


# ------------------------------------------------------------------ phases are kept apart
def test_tuning_labels_are_never_counted_in_any_metric(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        pool(conn, {"AUTO": 100, "REVIEW": 5, "JUST_BELOW": 3, "LOW": 2}, P2, "m")
        from pipeline.sample_labels import draw_tuning
        draw_tuning(conn, P2, copy.deepcopy({**CFG, "sampling": {**CFG["sampling"], "tuning_size": 10}}))
        tun = conn.execute("SELECT sample_id, holding_id_a, holding_id_b FROM label_samples WHERE phase = 'TUNING'").fetchall()
        for sid, a, b in tun:
            conn.execute("INSERT INTO labeled_pairs (sample_id, holding_id_a, holding_id_b, label, labeled_by, sampling_method) VALUES (%s, %s, %s, 'NO_MATCH', 't', 'BLOCKED')", (sid, a, b))
        frozen(conn)
        draw_heldout(conn, P2, CFG)
        drawn = dict(conn.execute("SELECT score_band, count(*) FROM label_samples WHERE phase = 'HELDOUT' GROUP BY 1").fetchall())
        label(conn, "HELDOUT", {band: ["MATCH"] * n for band, n in drawn.items()})
        rep = build_report(conn, CFG)
    assert rep["tuning"] == {"MATCH": 0, "NO_MATCH": 10, "UNSURE": 0}
    assert sum(sum(e["counts"].values()) for e in rep["heldout"]["bands"].values()) == sum(drawn.values()) <= 70
    assert drawn["AUTO"] == 60
    assert all(e["counts"]["NO_MATCH"] == 0 for e in rep["heldout"]["bands"].values())      # ten tuning NO_MATCH labels are not in them
    assert rep["heldout"]["bands"]["AUTO"]["worst_case"]["k"] == rep["heldout"]["bands"]["AUTO"]["worst_case"]["n"] == 60
    assert not rep["outoftime"]["drawn"]
    assert "TUNING (diagnostic, counts only, no precision" in render(rep) and "labeled 10: MATCH 0, NO_MATCH 10, UNSURE 0" in render(rep)


def test_out_of_time_is_reported_separately_and_never_pooled(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        scenario(conn)
        label(conn, "OUTOFTIME", {"AUTO": ["MATCH"] * 25 + ["NO_MATCH"] * 5, "REVIEW": ["MATCH", "UNSURE"], "JUST_BELOW": ["NO_MATCH", "NO_MATCH"], "LOW": []})
        rep = build_report(conn, CFG)
    h, o = rep["heldout"]["bands"], rep["outoftime"]["bands"]
    assert h["AUTO"]["counts"] == {"MATCH": 55, "NO_MATCH": 3, "UNSURE": 2}                    # unchanged by the out-of-time labels
    assert o["AUTO"]["counts"] == {"MATCH": 25, "NO_MATCH": 5, "UNSURE": 0} and (o["AUTO"]["frame"], o["AUTO"]["sampled"]) == (40, 30)
    assert (o["AUTO"]["excluded"]["k"], o["AUTO"]["excluded"]["n"]) == (25, 30)
    assert (o["LOW"]["frame"], o["LOW"]["sampled"], o["LOW"]["full"]) == (3, 0, False) and "excluded" not in o["LOW"]       # not sampled: no number
    assert sum(sum(e["counts"].values()) for e in o.values()) == 34 and sum(sum(e["counts"].values()) for e in h.values()) == 60 + 5 + 3 + 2
    text = render(rep)
    assert "OUT-OF-TIME (phase OUTOFTIME, prior quarter), reported separately, never pooled with held-out" in text
    assert "LOW: not sampled, frame 3" in text


def test_an_unlabeled_out_of_time_sample_is_not_reported_and_does_not_block_the_held_out_report(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        scenario(conn)
        rep = build_report(conn, CFG)
    assert rep["outoftime"]["bands"] is None and rep["outoftime"]["unlabeled"] == 30 + 2 + 2
    assert "not reported: 34 samples are unlabeled" in render(rep) and rep["heldout"]["bands"]["AUTO"]["frame"] == 100


# ------------------------------------------------------------------ refusals
def test_refuses_without_a_freeze_row(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        pool(conn, {"AUTO": 5}, P2, "m")
        with pytest.raises(SystemExit, match="no matcher_freeze row"):
            build_report(conn, CFG)


def test_25c_refuses_on_a_hash_mismatch_after_the_draw(migrated_db, tmp_path):
    root = make_root(tmp_path)
    cfg = copy.deepcopy(CFG)
    cfg["freeze"]["hashed_files"] = ["pipeline/a.py", "pipeline/b.py"]
    with psycopg.connect(migrated_db) as conn:
        pool(conn, {"AUTO": 5}, P2, "m")
        freeze(conn, cfg, root)
        draw_heldout(conn, P2, cfg, root)
        label(conn, "HELDOUT", {"AUTO": ["MATCH"] * 5, "REVIEW": [], "JUST_BELOW": [], "LOW": []})
        assert build_report(conn, cfg, root)["heldout"]["bands"]["AUTO"]["full"]
        (root / "pipeline/b.py").write_text("x = 'changed'\n")
        with pytest.raises(SystemExit, match="matcher changed since the freeze"):
            build_report(conn, cfg, root)
        (root / "pipeline/b.py").write_text("x = 'b'\n")
        cfg2 = copy.deepcopy(cfg)
        cfg2["bands"]["auto_min"] = 0.91
        with pytest.raises(SystemExit, match="matcher changed since the freeze"):
            build_report(conn, cfg2, root)


def test_refuses_when_a_stored_draw_hash_differs_from_the_freeze_row(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        scenario(conn, with_oot=False)
        conn.execute("UPDATE band_sizes SET matcher_config_hash = 'other' WHERE score_band = 'LOW'")
        with pytest.raises(SystemExit, match="band_sizes holds a hash that differs"):
            build_report(conn, CFG)


def test_refuses_when_a_held_out_sample_is_unlabeled_or_there_is_no_draw(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        pool(conn, {"AUTO": 70, "REVIEW": 5}, P2, "m")
        frozen(conn)
        with pytest.raises(SystemExit, match="no held-out draw"):
            build_report(conn, CFG)
        draw_heldout(conn, P2, CFG)
        with pytest.raises(SystemExit, match="65 held-out samples are unlabeled"):
            build_report(conn, CFG)
        label(conn, "HELDOUT", {"AUTO": ["MATCH"] * 59 + ["UNSURE"], "REVIEW": ["MATCH"] * 5, "JUST_BELOW": [], "LOW": []})
        assert build_report(conn, CFG)["heldout"]["bands"]["AUTO"]["counts"]["UNSURE"] == 1


# ------------------------------------------------------------------ no review leakage, no writes
def test_review_queue_status_and_scores_cannot_reach_any_number_and_nothing_is_written(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        scenario(conn)
        label(conn, "OUTOFTIME", {"AUTO": ["MATCH"] * 30, "REVIEW": ["MATCH"] * 2, "JUST_BELOW": ["NO_MATCH"] * 2, "LOW": []})
        first = render(build_report(conn, CFG))
        tables = ("label_samples", "labeled_pairs", "band_sizes", "outoftime_band_sizes", "matcher_freeze", "metric_results", "candidate_pairs")
        snap = {t: conn.execute(f"SELECT md5(string_agg(t::text, '|')) FROM {t} t").fetchone()[0] for t in tables if t != "candidate_pairs"}
        conn.execute("UPDATE candidate_pairs SET status = 'CONFIRMED', score = 0.01")
        assert render(build_report(conn, CFG)) == first
        conn.execute("DELETE FROM candidate_pairs")                                         # the evaluation does not need the table at all
        assert render(build_report(conn, CFG)) == first
        assert {t: conn.execute(f"SELECT md5(string_agg(t::text, '|')) FROM {t} t").fetchone()[0] for t in snap} == snap


def test_the_cli_prints_the_report(migrated_db, monkeypatch, capsys):
    monkeypatch.setenv("DATABASE_URL", migrated_db)
    with psycopg.connect(migrated_db) as conn:
        scenario(conn)
        conn.commit()
    assert evaluate.main() == 0
    out = capsys.readouterr().out
    assert "HELD-OUT (phase HELDOUT, measured period)" in out and "UNSURE excluded: 55 of 58" in out
