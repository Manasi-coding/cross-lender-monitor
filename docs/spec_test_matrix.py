"""Builds docs/spec_test_matrix.md: every SPEC section 13 test number mapped to the test files and names that cover it.
Each name is checked against the source text, so a renamed or deleted test shows as MISSING. Run: python docs/spec_test_matrix.py
Whether each test passes comes from the full pytest and vitest runs (see docs/overnight_report.md)."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

M = {
    1: ("Normalization, suffix variants", [("tests/test_normalize.py", "test_1_suffix_variants_normalize_to_a_comparable_form")]),
    2: ("Normalization, digits kept", [("tests/test_normalize.py", "test_2_digits_are_kept")]),
    3: ("Matching, true match", [("tests/test_match.py", "test_3_true_match_maturity_two_months_and_spread_20_bps_apart")]),
    4: ("Matching, instrument type mismatch", [("tests/test_match.py", "test_4_first_lien_versus_second_lien_is_never_a_candidate_whatever_the_name_score")]),
    5: ("Matching, band boundary 0.80", [("tests/test_match.py", "test_5_score_exactly_080_is_review_not_no_match")]),
    6: ("Idempotency", [("tests/test_idempotency.py", "test_second_ingest_changes_nothing")]),
    7: ("Schema drift", [("tests/test_schema_drift.py", "test_every_row_carries_source_url_and_row_order")]),
    8: ("Divergence, agreement", [("tests/test_compare.py", "test_8_and_9_divergence_agreement_and_flagged")]),
    9: ("Divergence, flagged", [("tests/test_compare.py", "test_8_and_9_divergence_agreement_and_flagged")]),
    10: ("Period end filter", [("tests/test_match.py", "test_10_pairs_from_different_period_ends_are_excluded_before_matching")]),
    11: ("Null and zero principal guard", [("tests/test_guards.py", "test_zero_principal_gives_null_and_a_reason_and_never_divides_by_zero"),
                                          ("tests/test_guards.py", "test_orcic_partially_unfunded_row_with_a_normal_ratio_keeps_its_value")]),
    12: ("API, endpoint shape (E5)", [("api/tests/read.test.js", "E5 returns the contract shape with sourceUrl on every row")]),
    13: ("API, review actions", [("api/tests/read.test.js", "E7 confirms a REVIEW pair in either id order"), ("api/tests/read.test.js", "E8 rejects AUTO, REVIEW and CONFIRMED pairs")]),
    14: ("Facility building excludes REVIEW and REJECTED", [("tests/test_compare.py", "test_14_review_and_no_match_pairs_never_cluster")]),
    15: ("labeled_pairs and candidate_pairs separation", [("api/tests/labeling.test.js", "SPEC 15: a pair confirmed in the review queue is not in labeled_pairs")]),
    16: ("REJECTED as cannot-link", [("tests/test_compare.py", "test_16_rejected_pair_is_a_cannot_link_and_the_lower_scoring_edge_is_skipped")]),
    17: ("Same-BDC collision routed to review", [("tests/test_compare.py", "test_17_same_bdc_collision_goes_to_review_not_to_a_facility")]),
    18: ("Borrower grouping", [("tests/test_compare.py", "test_18_borrower_grouping_is_exact_equality_of_the_cluster_name")]),
    19: ("Cluster naming determinism", [("tests/test_compare.py", "test_19_tied_names_resolve_to_the_alphabetically_first_and_two_runs_agree")]),
    20: ("Facility materialization", [("tests/test_compare.py", "test_20_three_holdings_with_one_zero_is_a_facility_with_excluded_count_1")]),
    21: ("Divergence boundaries", [("tests/test_compare.py", "test_21_divergence_boundaries_as_decimal")]),
    22: ("E5 contract and DATA_INTEGRITY", [("api/tests/read.test.js", "E5 returns 500 DATA_INTEGRITY when a facility has fewer than 2 included rows")]),
    23: ("E9 nulls and no review leakage", [("api/tests/metrics.test.js", "test 23: before evaluate.py every label-derived field is null"),
                                           ("tests/test_evaluate.py", "test_the_payload_ignores_candidate_pairs_status_and_tuning_labels")]),
    24: ("Labeling endpoints", [("api/tests/labeling.test.js", "E11 and E12 are not mounted: 404"), ("api/tests/labeling.test.js", "E11 never sends score, status, band, phase or draw order"),
                                ("api/tests/labeling.test.js", "E12 writes labeled_pairs only"), ("api/tests/contract.test.js", "E11 and E12 are 404 with the flag off")]),
    25: ("Freeze enforcement (a to e)", [("tests/test_heldout.py", "test_25a_the_draw_refuses_with_no_freeze_row"), ("tests/test_heldout.py", "test_25b_an_edit_to_a_hashed_file_or_config_key_after_the_freeze_refuses_the_draw"),
                                         ("tests/test_evaluate.py", "test_25c_refuses_on_a_hash_mismatch_after_the_draw"), ("tests/test_freeze.py", "test_25d_normalize_block_and_match_refuse_while_frozen"),
                                         ("tests/test_freeze.py", "test_25e_unfreeze_removes_the_freeze_and_every_held_out_artifact_and_keeps_tuning")]),
    26: ("Second quarter", [("tests/test_second_period.py", "test_second_quarter_loads_as_its_own_period_and_stays_out_of_labels"),
                            ("tests/test_freeze.py", "test_block_and_match_run_for_the_named_period_only_and_default_to_the_measured_one"),
                            ("tests/test_history.py", "test_35_a_normalized_prior_quarter_produces_no_block_pair_facility_or_sample")]),
    27: ("Exposure formula", [("tests/test_compare.py", "test_27_exposure_is_the_gap_in_points_times_the_smallest_included_principal")]),
    28: ("Exposure ordering", [("api/tests/read.test.js", "E4 sort=exposure orders by exposure, then divergence, then facility id")]),
    29: ("Signal boundaries", [("tests/test_compare.py", "test_29_spread_floor_maturity_and_cost_signals_fire_at_their_threshold_and_not_below"),
                              ("tests/test_compare.py", "test_29_rate_type_differs_only_for_fixed_against_a_non_null_floating_rate")]),
    30: ("Non accrual pattern", [("tests/test_guards.py", "test_non_accrual_flag_follows_the_filer_pattern_only"), ("tests/test_schema_drift.py", "test_ads_non_accrual_footnote_matches_the_configured_pattern"),
                                 ("tests/test_schema_drift.py", "test_hps_non_accrual_footnote_matches_the_configured_pattern"), ("tests/test_schema_drift.py", "test_orcic_non_accrual_footnote_matches_the_configured_pattern")]),
    31: ("E4 parameters", [("api/tests/read.test.js", "E4 filters by flag and searches; invalid flag or sort returns 400 (test 31)")]),
    32: ("E5 additions", [("api/tests/read.test.js", "test 32: E5 carries the dossier")]),
    33: ("Link rule (F3)", [("tests/test_history.py", "test_33_a_unique_key_links_exact_key_and_a_different_bdc_or_type_does_not"), ("tests/test_history.py", "test_33_an_ambiguous_key_links_only_on_a_unique_equal_maturity_and_otherwise_stays_unlinked")]),
    34: ("Persistence (F3)", [("tests/test_history.py", "test_34_persistence_labels_and_precedence"), ("tests/test_history.py", "test_34_compare_writes_facility_history_and_no_row_for_fewer_than_two_prior_marks")]),
    35: ("Prior quarter isolation (F3)", [("tests/test_history.py", "test_35_a_normalized_prior_quarter_produces_no_block_pair_facility_or_sample")]),
    36: ("History null versus NO_PRIOR", [("api/tests/read.test.js", "test 36: history is null and persistence is null when F3 is not built")]),
    37: ("Determinism", [("tests/test_compare.py", "test_37_two_runs_give_identical_signals_and_exposure"), ("tests/test_history.py", "test_37_two_compare_runs_give_identical_facility_history")]),
    38: ("E9 live fields", [("api/tests/metrics.test.js", "test 38: evidenceLift and fieldCoverage appear before evaluate.py")]),
}

rows, missing = [], []
for n, (title, refs) in sorted(M.items()):
    cells, ok = [], True
    for f, name in refs:
        text = (ROOT / f).read_text(encoding="utf-8") if (ROOT / f).exists() else ""
        found = bool(re.search(re.escape(name), text))
        ok &= found
        cells.append(f"`{f}`: {name}" + ("" if found else " (MISSING)"))
    if not ok:
        missing.append(n)
    rows.append(f"| {n} | {title} | " + "<br>".join(cells) + f" | {'present' if ok else 'MISSING'} |")
out = ["# SPEC section 13 test matrix", "", "Generated by `python docs/spec_test_matrix.py`. Present means every named test exists in the source. Pass or fail comes from the full test runs.", "",
       "| # | Test | Covered by | Status |", "|---|---|---|---|", *rows, "", f"Tests mapped: {len(M)} of 38. Missing: {missing if missing else 'none'}.", ""]
(ROOT / "docs" / "spec_test_matrix.md").write_text("\n".join(out), encoding="utf-8", newline="\n")
print(f"mapped {len(M)}, missing {missing}")
