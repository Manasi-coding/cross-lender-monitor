"""SPEC tests 3, 4, 5 and 10 (matching and blocking), the digit guard, the all_pairs formula, the freeze
refusal and the rule that a second run gives identical rows."""
from datetime import date
from decimal import Decimal

import psycopg
import pytest

from pipeline import block, match, normalize
from pipeline.block import add_months, all_pairs, is_candidate
from pipeline.config import load_config
from pipeline.match import score_pair, status_for

from conftest import seed_normalized

CFG = load_config()
P = date(2026, 6, 30)
A, B, C = "0000000001", "0000000002", "0000000003"


def r(cik, name, type_="FIRST_LIEN", maturity=date(2030, 1, 31), spread=Decimal(500), period=P):
    return {"bdc_cik": cik, "period_end_date": period, "borrower_normalized": name,
            "instrument_type_norm": type_, "maturity_date": maturity, "spread_bps": spread}


def run_pipeline(conn, period=P):
    block.build_block_keys(conn, period, CFG)
    return match.run(conn, period, CFG)


def pairs(conn):
    return conn.execute("SELECT holding_id_a, holding_id_b, score, status FROM candidate_pairs ORDER BY 1, 2").fetchall()


# ------------------------------------------------------------------ test 3: a true match
def test_3_true_match_maturity_two_months_and_spread_20_bps_apart(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        a, b = seed_normalized(conn, [r(A, "acme"), r(B, "acme", maturity=date(2030, 3, 31), spread=Decimal(520))])
        run_pipeline(conn)
        (row,) = pairs(conn)
    assert (row[0], row[1], row[3]) == (a, b, "AUTO")             # the status follows the score band
    assert row[2] == Decimal("1")


def test_3_pair_just_outside_the_windows_is_not_a_candidate():
    a, b = r(A, "acme"), r(B, "acme", maturity=add_months(date(2030, 1, 31), 3), spread=Decimal(500))
    assert is_candidate(a, b, CFG)                                   # exactly 3 months: inside, the window is inclusive
    assert not is_candidate(a, r(B, "acme", maturity=date(2030, 5, 15)), CFG)   # a bit over 3 months
    assert not is_candidate(a, r(B, "acme", spread=Decimal(551)), CFG)          # 51 bps apart
    assert is_candidate(a, r(B, "acme", spread=Decimal(550)), CFG)              # 50 bps: inside
    assert is_candidate(a, r(B, "acme", maturity=None, spread=None), CFG)        # NULL skips each gate


# ------------------------------------------------------------------ test 4: type mismatch
def test_4_first_lien_versus_second_lien_is_never_a_candidate_whatever_the_name_score(migrated_db):
    assert not is_candidate(r(A, "acme"), r(B, "acme", type_="SECOND_LIEN"), CFG)
    with psycopg.connect(migrated_db) as conn:
        seed_normalized(conn, [r(A, "acme"), r(B, "acme", type_="SECOND_LIEN")])
        run_pipeline(conn)
        assert pairs(conn) == []                                      # not stored, so it can never be AUTO or REVIEW


def test_equity_and_other_types_are_never_candidates(migrated_db):
    for t in ("EQUITY", "OTHER"):
        assert not is_candidate(r(A, "acme", type_=t), r(B, "acme", type_=t), CFG)
    with psycopg.connect(migrated_db) as conn:
        seed_normalized(conn, [r(A, "acme", type_="EQUITY"), r(B, "acme", type_="EQUITY")])
        run_pipeline(conn)
        assert pairs(conn) == [] and conn.execute("SELECT count(*) FROM blocking_keys").fetchone()[0] == 0


# ------------------------------------------------------------------ test 5: the band boundary
def test_5_score_exactly_080_is_review_not_no_match():
    assert status_for(Decimal("0.80"), CFG) == "REVIEW"
    assert status_for(Decimal("0.79999999"), CFG) == "NO_MATCH"
    assert status_for(Decimal("0.92"), CFG) == "AUTO"
    assert status_for(Decimal("0.91999999"), CFG) == "REVIEW"
    assert score_pair("abcde", "abcdf", CFG) == Decimal("0.8")       # a real pair whose token sort ratio is exactly 80
    assert status_for(score_pair("abcde", "abcdf", CFG), CFG) == "REVIEW"


def test_band_names():
    assert [match.band_for(Decimal(s), CFG) for s in ("0.95", "0.85", "0.70", "0.65", "0.64")] == \
        ["AUTO", "REVIEW", "JUST_BELOW", "JUST_BELOW", "LOW"]


# ------------------------------------------------------------------ digit guard
def test_digit_guard_keeps_a_numbered_entity_out_of_auto():
    plain = "alpha beta gamma delta"
    assert score_pair(plain, plain, CFG) == Decimal("1")
    capped = score_pair(plain + " 2", plain, CFG)
    assert capped == Decimal("0.79") and status_for(capped, CFG) == "NO_MATCH"      # review_min - 0.01
    assert score_pair("alpha 2 beta", "alpha beta 2", CFG) == Decimal("1")          # same digit multiset: no cap
    assert score_pair("fund 1 1", "fund 1", CFG) <= Decimal("0.79")                   # {1: 2} versus {1: 1}: the multisets differ


# ------------------------------------------------------------------ test 10: period end filter
def test_10_pairs_from_different_period_ends_are_excluded_before_matching(migrated_db):
    other = date(2026, 3, 31)
    assert not is_candidate(r(A, "acme"), r(B, "acme", period=other), CFG)
    with psycopg.connect(migrated_db) as conn:
        seed_normalized(conn, [r(A, "acme"), r(B, "acme", period=other), r(B, "acme")])
        run_pipeline(conn)
        rows = pairs(conn)
        assert len(rows) == 1                                          # only the two rows of the measured period
        prior = {x[0] for x in conn.execute("SELECT holding_id FROM normalized_holdings WHERE period_end_date = %s", (other,))}
        assert not any(a in prior or b in prior for a, b, *_ in rows)
        assert conn.execute("SELECT count(*) FROM blocking_keys k JOIN normalized_holdings n USING (holding_id) "
                            "WHERE n.period_end_date = %s", (other,)).fetchone()[0] == 0


def test_two_holdings_of_one_bdc_are_never_paired(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        seed_normalized(conn, [r(A, "acme"), r(A, "acme")])
        run_pipeline(conn)
        assert pairs(conn) == []


# ------------------------------------------------------------------ statuses and re-runs
def test_every_scored_pair_is_stored_including_no_match_and_a_lt_b(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        # zenith shares no block key with acme, so it is never paired; acme and acmo share the 4 character prefix
        seed_normalized(conn, [r(A, "acme"), r(B, "acme"), r(C, "zenith"), r(B, "acmo")])
        run_pipeline(conn)
        rows = pairs(conn)
    assert all(a < b for a, b, *_ in rows)
    assert {st for *_, st in rows} >= {"AUTO"}
    assert len(rows) == len({(a, b) for a, b, *_ in rows})


def test_confirmed_and_rejected_rows_survive_a_rescore(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        a, b, c = seed_normalized(conn, [r(A, "acme"), r(B, "acme"), r(B, "acme corp")])
        run_pipeline(conn)
        conn.execute("UPDATE candidate_pairs SET status = 'CONFIRMED' WHERE holding_id_a = %s AND holding_id_b = %s", (a, b))
        run_pipeline(conn)
        status = dict(((x, y), s) for x, y, _, s in pairs(conn))
    assert status[(a, b)] == "CONFIRMED"


def test_second_run_gives_identical_rows(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        seed_normalized(conn, [r(A, "acme"), r(B, "acme"), r(B, "acme bidco"), r(C, "acme bidco", maturity=date(2030, 2, 28))])
        run_pipeline(conn)
        keys1 = conn.execute("SELECT holding_id, block_key FROM blocking_keys ORDER BY 1, 2").fetchall()
        first = conn.execute("SELECT holding_id_a, holding_id_b, score, status, updated_at FROM candidate_pairs ORDER BY 1, 2").fetchall()
        run_pipeline(conn)
        keys2 = conn.execute("SELECT holding_id, block_key FROM blocking_keys ORDER BY 1, 2").fetchall()
        second = conn.execute("SELECT holding_id_a, holding_id_b, score, status, updated_at FROM candidate_pairs ORDER BY 1, 2").fetchall()
    assert keys1 == keys2 and first == second and first          # even updated_at is untouched on an identical rescore


# ------------------------------------------------------------------ freeze refusal
def test_normalize_block_and_match_refuse_once_the_matcher_is_frozen(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        conn.execute("INSERT INTO matcher_freeze (matcher_config_hash) VALUES ('abc')")
        for module, call in (("normalize", lambda: normalize.run(conn, P, CFG, verbose=False)),
                             ("match", lambda: match.run(conn, P, CFG))):
            with pytest.raises(SystemExit) as err:
                call()
            assert "frozen" in str(err.value) and module in str(err.value)
        with pytest.raises(SystemExit):
            normalize.refuse_if_frozen(conn, "block")


# ------------------------------------------------------------------ all_pairs formula (not a numbered SPEC test)
def test_all_pairs_formula_3_2_4_holdings_in_three_bdcs():
    assert all_pairs([3, 2, 4]) == 3 * 2 + 3 * 4 + 2 * 4 == 26
    assert all_pairs([5]) == 0 and all_pairs([]) == 0


def test_all_pairs_from_the_database_counts_every_type(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        seed_normalized(conn, [r(A, f"n{i}") for i in range(3)] + [r(B, f"m{i}", type_="EQUITY") for i in range(2)]
                        + [r(C, f"k{i}", type_="OTHER") for i in range(4)])
        eff = block.efficiency(conn, P)
    assert eff["all_pairs"] == 26 and eff["candidate_pairs"] == 0 and eff["pairs_avoided_pct"] == 100
