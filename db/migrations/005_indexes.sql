-- Extra indexes from phase_wise.md section 4.5 (beyond the primary keys and uniques in SPEC section 6).
CREATE INDEX idx_candidate_pairs_status_score ON candidate_pairs (status, score DESC);
CREATE INDEX idx_candidate_pairs_holding_b ON candidate_pairs (holding_id_b);
CREATE INDEX idx_normalized_holdings_period_bdc ON normalized_holdings (period_end_date, bdc_cik);
CREATE INDEX idx_blocking_keys_block_key ON blocking_keys (block_key);
CREATE INDEX idx_facility_comparisons_facility ON facility_comparisons (facility_id);
CREATE INDEX idx_canonical_facilities_borrower ON canonical_facilities (canonical_borrower_id);
CREATE INDEX idx_label_samples_phase_draw ON label_samples (phase, draw_order);
