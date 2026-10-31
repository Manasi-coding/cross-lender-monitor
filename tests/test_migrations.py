"""The migration set builds exactly the 23 SPEC section 6 tables, and a second run is a no-op."""
import psycopg

from pipeline.migrate import apply_migrations

EXPECTED_TABLES = {
    "raw_filings", "raw_holdings", "normalized_holdings", "blocking_keys", "candidate_pairs",
    "canonical_borrowers", "canonical_facilities", "holding_facility_map", "facility_comparisons",
    "facility_summary", "review_clusters", "review_cluster_members", "matcher_freeze",
    "label_samples", "band_sizes", "labeled_pairs", "blocking_recall_checks", "metric_results", "outoftime_band_sizes",
    "holding_history_links", "history_build", "facility_history", "history_link_checks",
}


def _tables(conn) -> set[str]:
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_name <> 'schema_migrations'"
    ).fetchall()
    return {r[0] for r in rows}


def test_empty_database_gets_exactly_23_tables(empty_db):
    with psycopg.connect(empty_db) as conn:
        applied = apply_migrations(conn)
        assert applied, "nothing was applied to an empty database"
        tables = _tables(conn)
    assert len(tables) == 23
    assert tables == EXPECTED_TABLES


def test_second_run_applies_nothing(empty_db):
    with psycopg.connect(empty_db) as conn:
        first = apply_migrations(conn)
        second = apply_migrations(conn)
        assert len(_tables(conn)) == 23
    assert first
    assert second == []


def test_matcher_freeze_is_a_singleton(migrated_db):
    with psycopg.connect(migrated_db) as conn:
        conn.execute("INSERT INTO matcher_freeze (matcher_config_hash) VALUES ('a')")
        raised = False
        try:
            with conn.transaction():
                conn.execute("INSERT INTO matcher_freeze (freeze_id, matcher_config_hash) VALUES (2, 'b')")
        except psycopg.errors.CheckViolation:
            raised = True
    assert raised
