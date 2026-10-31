"""F3: the within-BDC link (SPEC test 33), persistence (34), prior quarter isolation (35) and determinism with history (37)."""
from datetime import date
from decimal import Decimal

import psycopg
import pytest

from pipeline import block, compare, link_history
from pipeline.config import load_config
from pipeline.link_history import persistence, run

from conftest import seed_normalized

CFG = load_config()
P2, P1 = date(2026, 6, 30), date(2026, 3, 31)
B1, B2 = "0000000001", "0000000002"
D = Decimal


def row(cik, name, period, pct="98", maturity=date(2030, 1, 31), type_="FIRST_LIEN", **kw):
    r = {"bdc_cik": cik, "period_end_date": period, "borrower_normalized": name, "instrument_type_norm": type_,
         "maturity_date": maturity, "principal": D(1000), "fair_value_pct_par": None if pct is None else D(pct)}
    r.update(kw)
    return r


def links(conn):
    return conn.execute("SELECT holding_id, prior_holding_id, link_rule FROM holding_history_links ORDER BY holding_id").fetchall()


def auto(conn, a, b):
    conn.execute("INSERT INTO candidate_pairs (holding_id_a, holding_id_b, score, status) VALUES (%s, %s, 0.95, 'AUTO')", (min(a, b), max(a, b)))


# ------------------------------------------------------------------ 33: link rule
def test_33_a_unique_key_links_exact_key_and_a_different_bdc_or_type_does_not(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        cur, _other_bdc, _zeta, p, _q = seed_normalized(conn, [row(B1, "acme", P2), row(B2, "acme", P2), row(B1, "zeta", P2),
                                                               row(B1, "acme", P1), row(B1, "zeta", P1, type_="SECOND_LIEN")])
        res = run(conn, P2)
        assert links(conn) == [(cur, p, "EXACT_KEY")]                      # same BDC only; another instrument type is another key
        assert res["linked"] == 1 and res["by_rule"] == {"EXACT_KEY": 1, "EXACT_MATURITY": 0} and res["prior"] == P1
        assert conn.execute("SELECT linked, current_holdings, prior_period_end FROM history_build").fetchone() == (1, 3, P1)


def test_33_an_ambiguous_key_links_only_on_a_unique_equal_maturity_and_otherwise_stays_unlinked(migrated_db):
    m1, m2, m3 = date(2029, 1, 31), date(2030, 1, 31), date(2031, 1, 31)
    with psycopg.connect(migrated_db) as conn:
        c1, c2, _c3 = seed_normalized(conn, [row(B1, "acme", P2, maturity=m1), row(B1, "acme", P2, maturity=m2), row(B1, "acme", P2, maturity=m3)])
        p1, p2, _p3 = seed_normalized(conn, [row(B1, "acme", P1, maturity=m1), row(B1, "acme", P1, maturity=m2), row(B1, "acme", P1, maturity=date(2035, 1, 31))])
        run(conn, P2)
        got = links(conn)
    assert got == [(c1, p1, "EXACT_MATURITY"), (c2, p2, "EXACT_MATURITY")]  # the third has no equal maturity: unlinked, never guessed


def test_33_two_current_holdings_with_one_maturity_are_ambiguous_and_stay_unlinked(migrated_db):
    m = date(2030, 1, 31)
    with psycopg.connect(migrated_db) as conn:
        seed_normalized(conn, [row(B1, "acme", P2, maturity=m), row(B1, "acme", P2, maturity=m)])
        seed_normalized(conn, [row(B1, "acme", P1, maturity=m)])
        res = run(conn, P2)
        assert links(conn) == [] and res["unlinked"] == 2


def test_33_a_prior_holding_links_to_at_most_one_current_holding(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        seed_normalized(conn, [row(B1, "acme", P2, maturity=date(2030, 1, 31)), row(B1, "acme", P2, maturity=date(2030, 1, 31)),
                               row(B1, "zeta", P2), row(B1, "zeta", P2, maturity=date(2031, 1, 31))])
        seed_normalized(conn, [row(B1, "acme", P1, maturity=date(2030, 1, 31)), row(B1, "acme", P1, maturity=date(2031, 1, 31)),
                               row(B1, "zeta", P1), row(B1, "zeta", P1, maturity=date(2031, 1, 31))])
        run(conn, P2)
        priors = [p for _, p, _ in links(conn)]
        assert len(priors) == len(set(priors))
        h, p, _ = links(conn)[0]
        with pytest.raises(psycopg.errors.UniqueViolation):                # the database also refuses a second current holding for one prior
            conn.execute("INSERT INTO holding_history_links (holding_id, prior_holding_id, link_rule) VALUES (%s, %s, 'EXACT_KEY')",
                         (conn.execute("SELECT max(holding_id) FROM normalized_holdings").fetchone()[0], p))


def test_33_equal_key_with_unequal_known_currency_stays_unlinked_and_is_counted(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        c, = seed_normalized(conn, [row(B1, "acme", P2)])
        p, = seed_normalized(conn, [row(B1, "acme", P1)])
        conn.execute("UPDATE normalized_holdings SET principal_currency = 'USD' WHERE holding_id = %s", (c,))
        conn.execute("UPDATE normalized_holdings SET principal_currency = 'EUR' WHERE holding_id = %s", (p,))
        res = run(conn, P2)
        assert links(conn) == [] and res["currency_mismatch"] == 1
        conn.execute("UPDATE normalized_holdings SET principal_currency = NULL WHERE holding_id = %s", (p,))     # one unknown: the link is allowed
        run(conn, P2)
        assert [r[2] for r in links(conn)] == ["EXACT_KEY"]


def test_the_link_reads_only_normalized_holdings_and_never_candidate_pairs(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        seed_normalized(conn, [row(B1, "acme", P2)])
        seed_normalized(conn, [row(B1, "acme", P1)])
        conn.execute("ALTER TABLE candidate_pairs RENAME TO candidate_pairs_hidden")
        run(conn, P2)                                                      # works with the table gone
        assert len(links(conn)) == 1


def test_a_full_rebuild_replaces_old_links_and_refuses_without_a_prior_quarter(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        seed_normalized(conn, [row(B1, "acme", P2)])
        with pytest.raises(SystemExit, match="no normalized quarter before"):
            run(conn, P2)
        seed_normalized(conn, [row(B1, "acme", P1)])
        run(conn, P2)
        first = links(conn)
        run(conn, P2)
        assert links(conn) == first and conn.execute("SELECT count(*) FROM history_build").fetchone()[0] == 1


# ------------------------------------------------------------------ 34: persistence
@pytest.mark.parametrize("cur_pts, prior_pts, cur_flag, prior_flag, expected", [
    ("3.00", "2.01", "FLAGGED", "FLAGGED", "STABLE"),           # delta 0.99
    ("3.00", "2.00", "FLAGGED", "FLAGGED", "WIDENED"),          # delta 1.0
    ("3.00", "4.00", "FLAGGED", "FLAGGED", "NARROWED"),         # delta -1.0
    ("3.00", "3.99", "FLAGGED", "FLAGGED", "STABLE"),           # delta -0.99
    ("0.50", "3.00", "AGREEMENT", "FLAGGED", "CLOSED"),         # CLOSED takes precedence over NARROWED
    ("0.50", "0.40", "AGREEMENT", "AGREEMENT", "STABLE"),
    ("0.50", "1.50", "AGREEMENT", "MILD", "CLOSED"),
])
def test_34_persistence_labels_and_precedence(cur_pts, prior_pts, cur_flag, prior_flag, expected):
    assert persistence(cur_flag, D(cur_pts), prior_flag, D(prior_pts), D("1.0")) == expected


def test_34_compare_writes_facility_history_and_no_row_for_fewer_than_two_prior_marks(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        a, b, c, d = seed_normalized(conn, [row(B1, "acme", P2, pct="98"), row(B2, "acme", P2, pct="95"),
                                            row(B1, "zeta", P2, pct="98"), row(B2, "zeta", P2, pct="98")])
        seed_normalized(conn, [row(B1, "acme", P1, pct="98"), row(B2, "acme", P1, pct="97.5"),     # prior divergence 0.5, now 3.0: WIDENED
                               row(B1, "zeta", P1, pct="98"), row(B2, "zeta", P1, pct=None)])     # only one prior mark: NO_PRIOR
        auto(conn, a, b)
        auto(conn, c, d)
        run(conn, P2)
        compare.run(conn, P2, CFG)
        got = conn.execute("SELECT b.canonical_name, h.prior_period_end, h.prior_lender_count, h.prior_divergence_pts, h.prior_divergence_flag, h.persistence "
                           "FROM facility_history h JOIN canonical_facilities f USING (facility_id) JOIN canonical_borrowers b USING (canonical_borrower_id)").fetchall()
    assert got == [("acme", P1, 2, D("0.5"), "AGREEMENT", "WIDENED")]     # zeta has no row: NO_PRIOR by absence


def test_without_a_history_build_compare_writes_no_history(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        a, b = seed_normalized(conn, [row(B1, "acme", P2), row(B2, "acme", P2, pct="95")])
        auto(conn, a, b)
        compare.run(conn, P2, CFG)
        assert conn.execute("SELECT count(*) FROM facility_history").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM history_build").fetchone()[0] == 0


# ------------------------------------------------------------------ 35: prior quarter isolation
def test_35_a_normalized_prior_quarter_produces_no_block_pair_facility_or_sample(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        seed_normalized(conn, [row(B1, "acme", P2), row(B2, "acme", P2)])
        seed_normalized(conn, [row(B1, "acme", P1), row(B2, "acme", P1)])
        block.build_block_keys(conn, P2, CFG)                                 # the measured period only, as block.py runs it
        for x, y in block.candidate_pairs(conn, P2, CFG):
            auto(conn, x, y)
        run(conn, P2)
        compare.run(conn, P2, CFG)
        prior_ids = {r[0] for r in conn.execute("SELECT holding_id FROM normalized_holdings WHERE period_end_date = %s", (P1,)).fetchall()}

        def used(sql):
            return {x for r in conn.execute(sql).fetchall() for x in r}
        assert not prior_ids & used("SELECT holding_id FROM blocking_keys")
        assert not prior_ids & used("SELECT holding_id_a, holding_id_b FROM candidate_pairs")
        assert not prior_ids & used("SELECT holding_id FROM holding_facility_map")
        assert not prior_ids & used("SELECT holding_id_a, holding_id_b FROM label_samples")
        assert conn.execute("SELECT count(*) FROM facility_comparisons WHERE period_end_date = %s", (P1,)).fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM canonical_facilities").fetchone()[0] == 1


# ------------------------------------------------------------------ 37: determinism with history
def test_37_two_compare_runs_give_identical_facility_history(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        a, b = seed_normalized(conn, [row(B1, "acme", P2, pct="98"), row(B2, "acme", P2, pct="95")])
        seed_normalized(conn, [row(B1, "acme", P1, pct="98"), row(B2, "acme", P1, pct="97")])
        auto(conn, a, b)
        run(conn, P2)
        compare.run(conn, P2, CFG)
        first = conn.execute("SELECT * FROM facility_history ORDER BY 1").fetchall()
        compare.run(conn, P2, CFG)
        assert conn.execute("SELECT * FROM facility_history ORDER BY 1").fetchall() == first and len(first) == 1


# ------------------------------------------------------------------ the hand check tooling
def test_record_stores_a_check_only_for_a_stored_link_and_updates_in_place(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        c, = seed_normalized(conn, [row(B1, "acme", P2)])
        p, = seed_normalized(conn, [row(B1, "acme", P1)])
        run(conn, P2)
        with pytest.raises(SystemExit, match="not a stored link"):
            link_history.record(conn, c, c, "MATCH", "me")
        with pytest.raises(SystemExit, match="label must be"):
            link_history.record(conn, c, p, "YES", "me")
        link_history.record(conn, c, p, "UNSURE", "me")
        link_history.record(conn, c, p, "MATCH", "me")
        assert conn.execute("SELECT label, labeled_by FROM history_link_checks").fetchall() == [("MATCH", "me")]


def test_worksheet_lists_a_seeded_sample_of_links_with_raw_attributes(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        seed_normalized(conn, [row(B1, f"b{i:02d}", per) for per in (P2, P1) for i in range(40)])
        run(conn, P2)
        text = link_history.worksheet_text(conn, CFG)
        again = link_history.worksheet_text(conn, CFG)
    assert text == again and text.count("\n| ") == 30 + 1 and "seed 1" in text
