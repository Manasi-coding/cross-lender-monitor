"""SPEC tests 8, 9, 14, 16, 17, 18, 19, 20 and 21 (compare.py), the identical-rows rule, and the read-only rules
for candidate_pairs and the label tables. Inputs for 16 to 21 are the ones in SPEC section 13."""
from datetime import date
from decimal import Decimal

import psycopg
import pytest

from pipeline import compare
from pipeline.compare import flag_for
from pipeline.config import load_config

from conftest import seed_normalized

CFG = load_config()
P = date(2026, 6, 30)
B1, B2, B3, B4 = "0000000001", "0000000002", "0000000003", "0000000004"


def h(cik, name="acme", pct="98", principal="1000", **kw):
    r = {"bdc_cik": cik, "period_end_date": kw.pop("period", P), "borrower_normalized": name, "instrument_type_norm": "FIRST_LIEN",
         "principal": Decimal(principal), "fair_value_pct_par": None if pct is None else Decimal(pct)}
    r.update(kw)
    return r


def pair(conn, a, b, status="AUTO", score="0.95"):
    a, b = min(a, b), max(a, b)
    conn.execute("INSERT INTO candidate_pairs (holding_id_a, holding_id_b, score, status) VALUES (%s, %s, %s, %s)", (a, b, Decimal(score), status))


def facilities(conn):
    return conn.execute("SELECT facility_id FROM canonical_facilities ORDER BY 1").fetchall()


def members(conn):
    out = {}
    for hid, fid in conn.execute("SELECT holding_id, facility_id FROM holding_facility_map ORDER BY 1").fetchall():
        out.setdefault(fid, []).append(hid)
    return sorted(out.values())


def curated(conn):
    return {
        "borrowers": conn.execute("SELECT canonical_borrower_id, canonical_name, period_end_date FROM canonical_borrowers ORDER BY 1").fetchall(),
        "facilities": conn.execute("SELECT * FROM canonical_facilities ORDER BY 1").fetchall(),
        "map": conn.execute("SELECT * FROM holding_facility_map ORDER BY 1").fetchall(),
        "comparisons": conn.execute("SELECT * FROM facility_comparisons ORDER BY 1, 2").fetchall(),
        "summary": conn.execute("SELECT * FROM facility_summary ORDER BY 1").fetchall(),
        "review": conn.execute("SELECT * FROM review_clusters ORDER BY 1").fetchall(),
        "review_members": conn.execute("SELECT * FROM review_cluster_members ORDER BY 1, 2").fetchall(),
    }


# ------------------------------------------------------------------ SPEC 8, 9, 21: divergence
def test_8_and_9_divergence_agreement_and_flagged(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        a, b, c, d = seed_normalized(conn, [h(B1, pct="98.0"), h(B2, pct="98.5"), h(B1, "zed", pct="95.0"), h(B2, "zed", pct="98.0")])
        pair(conn, a, b)
        pair(conn, c, d)
        compare.run(conn, P, CFG)
        rows = dict(conn.execute("SELECT divergence_pts, divergence_flag FROM facility_summary").fetchall())
    assert rows == {Decimal("0.5"): "AGREEMENT", Decimal("3.0"): "FLAGGED"}


def test_21_divergence_boundaries_as_decimal():
    mild, flagged = compare.cutoffs(CFG)
    assert (mild, flagged) == (Decimal("1.0"), Decimal("2.0"))
    got = [flag_for(Decimal(x), mild, flagged) for x in ("0.99", "1.0", "1.99", "2.0")]
    assert got == ["AGREEMENT", "MILD", "MILD", "FLAGGED"]


def test_21_boundaries_end_to_end_through_the_database(migrated_db):
    diffs = ["0.99", "1.0", "1.99", "2.0"]
    with psycopg.connect(migrated_db) as conn:
        rows = []
        for i, d in enumerate(diffs):
            rows += [h(B1, f"n{i}", pct="90"), h(B2, f"n{i}", pct=str(Decimal("90") + Decimal(d)))]
        ids = seed_normalized(conn, rows)
        for i in range(4):
            pair(conn, ids[2 * i], ids[2 * i + 1])
        compare.run(conn, P, CFG)
        got = conn.execute("SELECT divergence_pts, divergence_flag FROM facility_summary ORDER BY divergence_pts").fetchall()
    assert [(str(d), f) for d, f in got] == [("0.99", "AGREEMENT"), ("1.0", "MILD"), ("1.99", "MILD"), ("2.0", "FLAGGED")]


# ------------------------------------------------------------------ SPEC 14
def test_14_review_and_no_match_pairs_never_cluster(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        a, b, c, d = seed_normalized(conn, [h(B1), h(B2), h(B1, "zed"), h(B2, "zed")])
        pair(conn, a, b, "REVIEW", "0.85")
        pair(conn, c, d, "NO_MATCH", "0.50")
        res = compare.run(conn, P, CFG)
        assert res["clusters"] == 0 and facilities(conn) == [] and members(conn) == []


# ------------------------------------------------------------------ SPEC 16
def test_16_rejected_pair_is_a_cannot_link_and_the_lower_scoring_edge_is_skipped(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        a, b, c = seed_normalized(conn, [h(B1), h(B2), h(B3)])
        pair(conn, a, c, "AUTO", "0.97")
        pair(conn, b, c, "AUTO", "0.93")
        pair(conn, a, b, "REJECTED", "0.60")
        res = compare.run(conn, P, CFG)
        assert members(conn) == [[a, c]]                                    # A and B never share a facility
    assert [(s["a"], s["b"]) for s in res["skipped"]] == [(b, c)]
    assert any(f"skipped edge {b}-{c}" in line and "cannot-link" in line for line in res["log"])


def test_16_equal_scores_break_ties_by_ascending_ids(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        a, b, c = seed_normalized(conn, [h(B1), h(B2), h(B3)])
        pair(conn, a, c, "AUTO", "0.95")
        pair(conn, b, c, "AUTO", "0.95")
        pair(conn, a, b, "REJECTED", "0.60")
        res = compare.run(conn, P, CFG)
        assert members(conn) == [[a, c]] and [(s["a"], s["b"]) for s in res["skipped"]] == [(b, c)]


def test_16_confirmed_edges_go_first_even_with_a_lower_score(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        a, b, c = seed_normalized(conn, [h(B1), h(B2), h(B3)])
        pair(conn, a, c, "CONFIRMED", "0.81")
        pair(conn, b, c, "AUTO", "0.99")
        pair(conn, a, b, "REJECTED", "0.60")
        compare.run(conn, P, CFG)
        assert members(conn) == [[a, c]]


# ------------------------------------------------------------------ SPEC 17
def test_17_same_bdc_collision_goes_to_review_not_to_a_facility(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        a, b, c = seed_normalized(conn, [h(B1), h(B1), h(B2)])               # A and B are from one BDC
        pair(conn, a, c)
        pair(conn, b, c)
        res = compare.run(conn, P, CFG)
        assert facilities(conn) == [] and members(conn) == []
        assert conn.execute("SELECT reason FROM review_clusters").fetchall() == [("SAME_BDC_COLLISION",)]
        assert [r[0] for r in conn.execute("SELECT holding_id FROM review_cluster_members ORDER BY 1").fetchall()] == [a, b, c]
    assert len(res["collisions"]) == 1


# ------------------------------------------------------------------ SPEC 18
def test_18_borrower_grouping_is_exact_equality_of_the_cluster_name(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        ids = seed_normalized(conn, [h(B1, "acme holdings 2"), h(B2, "acme holdings 2"), h(B1, "acme holdings"), h(B2, "acme holdings"),
                                     h(B1, "zed"), h(B2, "zed")])
        for i in range(3):
            pair(conn, ids[2 * i], ids[2 * i + 1])
        compare.run(conn, P, CFG)
        names = [r[0] for r in conn.execute("SELECT canonical_name FROM canonical_borrowers ORDER BY 1").fetchall()]
        per_borrower = conn.execute("SELECT canonical_borrower_id, count(*) FROM canonical_facilities GROUP BY 1").fetchall()
    assert names == ["acme holdings", "acme holdings 2", "zed"]              # the two acme names are separate borrowers
    assert len(per_borrower) == 3 and {n for _, n in per_borrower} == {1}    # a single-facility borrower still exists


def test_two_facilities_of_one_borrower_share_a_borrower_row(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        a, b, c, d = seed_normalized(conn, [h(B1), h(B2), h(B1, instrument_type_norm="REVOLVER"), h(B2, instrument_type_norm="REVOLVER")])
        pair(conn, a, b)
        pair(conn, c, d)
        compare.run(conn, P, CFG)
        assert conn.execute("SELECT count(*) FROM canonical_borrowers").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM canonical_facilities").fetchone()[0] == 2


# ------------------------------------------------------------------ SPEC 19
def test_19_tied_names_resolve_to_the_alphabetically_first_and_two_runs_agree(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        a, b, c, d, e, f = seed_normalized(conn, [h(B1, "zeta corp"), h(B2, "alpha corp"),                       # 1 to 1
                                                   h(B1, "b name"), h(B2, "a name"), h(B3, "b name"), h(B4, "a name")])  # 2 to 2
        pair(conn, a, b)
        pair(conn, c, d)
        pair(conn, d, e)
        pair(conn, e, f)
        compare.run(conn, P, CFG)
        first = curated(conn)
        compare.run(conn, P, CFG)
        second = curated(conn)
    assert [r[1] for r in first["borrowers"]] == ["a name", "alpha corp"]
    assert first == second


# ------------------------------------------------------------------ SPEC 20
def test_20_cluster_with_fewer_than_two_usable_marks_is_not_a_facility(migrated_db):
    zero = dict(principal="0", pct=None, excluded_reason="ZERO_OR_NULL_PRINCIPAL")
    with psycopg.connect(migrated_db) as conn:
        a, b = seed_normalized(conn, [h(B1), h(B2, **zero)])
        pair(conn, a, b)
        res = compare.run(conn, P, CFG)
        assert facilities(conn) == [] and conn.execute("SELECT count(*) FROM facility_comparisons").fetchone()[0] == 0
    assert len(res["failed"]) == 1 and any("not a facility" in line for line in res["log"])


def test_20_three_holdings_with_one_zero_is_a_facility_with_excluded_count_1(migrated_db):
    zero = dict(principal="0", pct=None, excluded_reason="ZERO_OR_NULL_PRINCIPAL")
    with psycopg.connect(migrated_db) as conn:
        a, b, c = seed_normalized(conn, [h(B1, pct="97"), h(B2, pct="98"), h(B3, **zero)])
        pair(conn, a, b)
        pair(conn, b, c)
        compare.run(conn, P, CFG)
        lender, excluded, div = conn.execute("SELECT lender_count, excluded_count, divergence_pts FROM facility_summary").fetchone()
        rows = conn.execute("SELECT holding_id, fair_value_pct_par, excluded_reason FROM facility_comparisons ORDER BY 1").fetchall()
    assert (lender, excluded, div) == (2, 1, Decimal("1")) and len(rows) == 3
    assert rows[2] == (c, None, "ZERO_OR_NULL_PRINCIPAL")                   # kept and flagged, not used in divergence


# ------------------------------------------------------------------ attributes, carried fields, scope
def test_attributes_spread_copy_and_source_url(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        a, b, c = seed_normalized(conn, [
            h(B1, spread_bps=Decimal(550), maturity_date=date(2031, 5, 31), reference_rate="SOFR"),
            h(B2, spread_bps=Decimal(560), maturity_date=date(2031, 3, 31), reference_rate="EURIBOR"),
            h(B3, spread_bps=None, maturity_date=None, reference_rate="SOFR")])
        pair(conn, a, b)
        pair(conn, b, c)
        compare.run(conn, P, CFG)
        fac = conn.execute("SELECT instrument_type_norm, reference_rate, maturity_bucket FROM canonical_facilities").fetchone()
        spreads = [r[0] for r in conn.execute("SELECT spread_bps_total FROM facility_comparisons ORDER BY holding_id").fetchall()]
        urls = {r[0] for r in conn.execute("SELECT source_url FROM facility_comparisons").fetchall()}
        names = {r[0] for r in conn.execute("SELECT bdc_name FROM facility_comparisons").fetchall()}
    assert fac == ("FIRST_LIEN", "SOFR", date(2031, 3, 31))                 # most frequent rate, earliest maturity
    assert spreads == [Decimal(550), Decimal(560), None]                    # a copy of spread_bps, never plus pik_bps
    assert urls == {"https://example.test/f"} and names == {"BDC " + B1, "BDC " + B2, "BDC " + B3}


def test_only_the_measured_period_is_built(migrated_db):
    other = date(2026, 3, 31)
    with psycopg.connect(migrated_db) as conn:
        a, b, c, d = seed_normalized(conn, [h(B1), h(B2), h(B1, "later", period=other), h(B2, "later", period=other)])
        pair(conn, a, b)
        pair(conn, c, d)
        compare.run(conn, P, CFG)
        assert members(conn) == [[a, b]]
        assert {r[0] for r in conn.execute("SELECT period_end_date FROM canonical_borrowers").fetchall()} == {P}


# ------------------------------------------------------------------ reruns, ids, read-only rules
def test_two_runs_give_identical_ids_and_rows(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        ids = seed_normalized(conn, [h(B1, "n1", pct="97"), h(B2, "n1", pct="99.5"), h(B1, "n2"), h(B2, "n2", pct="90"), h(B3, "n2", pct="91"),
                                     h(B1, "n3"), h(B1, "n3"), h(B2, "n3")])
        pair(conn, ids[0], ids[1])
        pair(conn, ids[2], ids[3])
        pair(conn, ids[3], ids[4])
        pair(conn, ids[5], ids[7])
        pair(conn, ids[6], ids[7])
        compare.run(conn, P, CFG)
        first = curated(conn)
        compare.run(conn, P, CFG)
        second = curated(conn)
    assert first == second and len(first["facilities"]) == 2 and len(first["review"]) == 1
    assert [r[0] for r in first["facilities"]] == [1, 2] and [r[0] for r in first["borrowers"]] == [1, 2]


def test_compare_never_writes_candidate_pairs_or_label_tables_and_labels_do_not_cluster(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        a, b, c, d = seed_normalized(conn, [h(B1), h(B2), h(B1, "zed"), h(B2, "zed")])
        pair(conn, a, b, "AUTO", "0.96")
        pair(conn, c, d, "REVIEW", "0.85")
        sid = conn.execute("INSERT INTO label_samples (holding_id_a, holding_id_b, phase, draw_order) VALUES (%s, %s, 'TUNING', 1) RETURNING sample_id",
                           (c, d)).fetchone()[0]
        conn.execute("INSERT INTO labeled_pairs (sample_id, holding_id_a, holding_id_b, label, labeled_by, sampling_method) "
                     "VALUES (%s, %s, %s, 'MATCH', 't', 'BLOCKED')", (sid, c, d))        # a MATCH label on a REVIEW pair
        tables = ("candidate_pairs", "label_samples", "labeled_pairs", "matcher_freeze")
        before = {t: conn.execute(f"SELECT * FROM {t} ORDER BY 1, 2").fetchall() for t in tables}
        compare.run(conn, P, CFG)
        after = {t: conn.execute(f"SELECT * FROM {t} ORDER BY 1, 2").fetchall() for t in tables}
        assert members(conn) == [[a, b]]                                        # the label did not create a facility
    assert before == after


def test_rebuild_is_one_transaction_a_failure_keeps_the_old_state(migrated_db, monkeypatch):
    with psycopg.connect(migrated_db) as conn:
        a, b = seed_normalized(conn, [h(B1), h(B2)])
        pair(conn, a, b)
        compare.run(conn, P, CFG)
        old = curated(conn)
        monkeypatch.setattr(compare, "flag_for", lambda *x: (_ for _ in ()).throw(RuntimeError("boom")))
        with pytest.raises(RuntimeError):
            compare.run(conn, P, CFG)
        assert curated(conn) == old


# ------------------------------------------------------------------ the collision test counts marked holdings only
UNFUNDED = dict(pct=None, excluded_reason="UNFUNDED_COMMITMENT")


def test_unmarked_same_bdc_holdings_do_not_make_a_collision(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        a, h1, u1, u2 = seed_normalized(conn, [h(B1, pct="97"), h(B2, pct="99"), h(B2, **UNFUNDED), h(B2, **UNFUNDED)])
        pair(conn, a, h1)
        pair(conn, a, u1)
        pair(conn, a, u2)
        res = compare.run(conn, P, CFG)
        lender, excluded = conn.execute("SELECT lender_count, excluded_count FROM facility_summary").fetchone()
        rows = conn.execute("SELECT holding_id, fair_value_pct_par, excluded_reason FROM facility_comparisons ORDER BY 1").fetchall()
        assert conn.execute("SELECT count(*) FROM review_clusters").fetchone()[0] == 0
        assert members(conn) == [[a, h1, u1, u2]]
    assert (lender, excluded) == (2, 2) and res["collisions"] == []
    assert [r[2] for r in rows] == [None, None, "UNFUNDED_COMMITMENT", "UNFUNDED_COMMITMENT"]   # kept with their reason


def test_two_marked_holdings_from_one_bdc_still_go_to_review_with_every_member(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        a, h1, h2, u1 = seed_normalized(conn, [h(B1, pct="97"), h(B2, pct="99"), h(B2, pct="98"), h(B2, **UNFUNDED)])
        pair(conn, a, h1)
        pair(conn, a, h2)
        pair(conn, a, u1)
        res = compare.run(conn, P, CFG)
        assert facilities(conn) == [] and conn.execute("SELECT count(*) FROM facility_comparisons").fetchone()[0] == 0
        got = [r[0] for r in conn.execute("SELECT holding_id FROM review_cluster_members ORDER BY 1").fetchall()]
    assert got == [a, h1, h2, u1] and len(res["collisions"]) == 1                # the unmarked holding is a member too


def test_one_marked_holding_with_only_unmarked_partners_is_not_a_facility(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        a, u1 = seed_normalized(conn, [h(B1, pct="97"), h(B2, **UNFUNDED)])
        pair(conn, a, u1)
        res = compare.run(conn, P, CFG)
        assert facilities(conn) == [] and conn.execute("SELECT count(*) FROM review_clusters").fetchone()[0] == 0
    assert len(res["failed"]) == 1


# ------------------------------------------------------------------ exposure_usd (v2 F1, tests 27 and 28 on the compare side)
def test_27_exposure_is_the_gap_in_points_times_the_smallest_included_principal(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        a, b, c, d, e = seed_normalized(conn, [h(B1, "two lender", pct="95", principal="1000000"), h(B2, "two lender", pct="98", principal="4000000"),
                                               h(B1, "three lender", pct="90", principal="5000000"), h(B2, "three lender", pct="95", principal="2000000"),
                                               h(B3, "three lender", pct="99", principal="8000000")])
        pair(conn, a, b)
        pair(conn, c, d)
        pair(conn, d, e)
        compare.run(conn, P, CFG)
        got = dict(conn.execute(
            "SELECT b.canonical_name, s.exposure_usd FROM facility_summary s JOIN canonical_facilities f USING (facility_id) "
            "JOIN canonical_borrowers b USING (canonical_borrower_id)").fetchall())
    assert got["two lender"] == Decimal("30000")        # 3.0 points of 1,000,000
    assert got["three lender"] == Decimal("180000")     # 9.0 points of the smallest principal, 2,000,000


def test_exposure_ignores_an_excluded_holding_and_uses_only_included_principals(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        a, b, c = seed_normalized(conn, [h(B1, pct="90", principal="5000000"), h(B2, pct="94", principal="3000000"),
                                         h(B3, pct=None, principal="10", excluded_reason="UNFUNDED_COMMITMENT")])
        pair(conn, a, b)
        pair(conn, b, c)
        compare.run(conn, P, CFG)
        (exposure,) = conn.execute("SELECT exposure_usd FROM facility_summary").fetchone()
    assert exposure == Decimal("120000")                # 4.0 points of 3,000,000; the excluded holding's principal of 10 is not the minimum


def test_no_facility_has_zero_exposure_only_because_compare_did_not_set_it(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        col = conn.execute("SELECT is_nullable, column_default FROM information_schema.columns "
                           "WHERE table_name = 'facility_summary' AND column_name = 'exposure_usd'").fetchone()
        assert col == ("NO", None)                       # NOT NULL and no default: an unset value fails instead of becoming 0
        rows = []
        for i, (x, y) in enumerate([("90", "95"), ("90", "91"), ("97", "97"), ("80.5", "99")]):    # divergence 5, 1, 0 and 18.5
            rows += [h(B1, f"n{i}", pct=x, principal=str(1000000 * (i + 1))), h(B2, f"n{i}", pct=y, principal=str(2000000 * (i + 1)))]
        ids = seed_normalized(conn, rows)
        for i in range(4):
            pair(conn, ids[2 * i], ids[2 * i + 1])
        compare.run(conn, P, CFG)
        bad = conn.execute(
            "SELECT s.facility_id FROM facility_summary s WHERE s.exposure_usd = 0 AND s.divergence_pts > 0").fetchall()
        recomputed = conn.execute(
            "SELECT s.facility_id FROM facility_summary s JOIN (SELECT facility_id, MIN(principal) m FROM facility_comparisons "
            "WHERE fair_value_pct_par IS NOT NULL GROUP BY 1) x USING (facility_id) "
            "WHERE s.exposure_usd <> s.divergence_pts / 100 * x.m").fetchall()
        zero = conn.execute("SELECT count(*) FROM facility_summary WHERE exposure_usd = 0").fetchone()[0]
        total = conn.execute("SELECT count(*) FROM facility_summary").fetchone()[0]
    assert bad == [] and recomputed == []
    assert (zero, total) == (1, 4)                       # only the facility whose marks agree exactly has exposure 0


def test_migration_009_backfills_existing_facilities_from_facility_comparisons(empty_db, tmp_path):
    import shutil
    from pipeline.migrate import MIGRATIONS_DIR, apply_migrations
    before = tmp_path / "before"
    before.mkdir()
    for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if f.name < "009":
            shutil.copy(f, before / f.name)
    with psycopg.connect(empty_db) as conn:
        apply_migrations(conn, before)                   # the schema as it was before 009, with a facility already in it
        a, b = seed_normalized(conn, [h(B1, pct="90", principal="5000000"), h(B2, pct="95", principal="2000000")])
        conn.execute("INSERT INTO canonical_borrowers (canonical_name, period_end_date) VALUES ('x', %s)", (P,))
        conn.execute("INSERT INTO canonical_facilities (canonical_borrower_id, period_end_date, instrument_type_norm) VALUES (1, %s, 'FIRST_LIEN')", (P,))
        for hid, cik, pr, pct in ((a, B1, 5000000, 90), (b, B2, 2000000, 95)):
            conn.execute("INSERT INTO facility_comparisons (facility_id, holding_id, period_end_date, bdc_cik, bdc_name, principal, fair_value_pct_par, source_url) "
                         "VALUES (1, %s, %s, %s, 'x', %s, %s, 'u')", (hid, P, cik, pr, pct))
        conn.execute("INSERT INTO facility_summary VALUES (1, 2, 0, 5, 'FLAGGED')")
        applied = apply_migrations(conn)
        assert applied == [f.name for f in sorted(MIGRATIONS_DIR.glob("*.sql")) if f.name >= "009"]
        assert conn.execute("SELECT exposure_usd FROM facility_summary").fetchone()[0] == Decimal("100000")     # 5 points of 2,000,000
