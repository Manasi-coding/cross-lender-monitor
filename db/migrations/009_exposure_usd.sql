-- v2 F1 (exposure triage). exposure_usd = (divergence_pts / 100) * MIN(principal over included holdings), a ranking key.
-- compare.py writes it on every rebuild. The column is added empty, backfilled from facility_comparisons for rows that
-- already exist (so no default value stands in for a number that was never computed), then made NOT NULL.
-- The dossier columns and signal_codes are Day 9 work and arrive in a later migration.
ALTER TABLE facility_summary ADD COLUMN exposure_usd NUMERIC;

UPDATE facility_summary s
   SET exposure_usd = (s.divergence_pts / 100) * m.min_principal
  FROM (SELECT facility_id, MIN(principal) AS min_principal
          FROM facility_comparisons
         WHERE fair_value_pct_par IS NOT NULL
         GROUP BY facility_id) m
 WHERE m.facility_id = s.facility_id;

ALTER TABLE facility_summary ALTER COLUMN exposure_usd SET NOT NULL;
ALTER TABLE facility_summary ADD CONSTRAINT facility_summary_exposure_nonneg CHECK (exposure_usd >= 0);

CREATE INDEX idx_fs_exposure ON facility_summary (exposure_usd DESC, facility_id);
CREATE INDEX idx_fs_flag     ON facility_summary (divergence_flag);
