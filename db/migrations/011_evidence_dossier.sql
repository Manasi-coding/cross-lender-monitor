-- v2 F2 (evidence dossier). Additive. facility_comparisons gains the row-level dossier columns, facility_summary gains signal_codes.
-- compare.py writes them on every rebuild; rows that exist before the next rebuild keep NULL dossier values (not disclosed) and an empty signal list.
-- Row-level NULL means not disclosed in the filing. cost_pct_par is set only when fair_value_pct_par is set.
ALTER TABLE facility_comparisons
  ADD COLUMN IF NOT EXISTS cost          NUMERIC,
  ADD COLUMN IF NOT EXISTS cost_pct_par  NUMERIC,
  ADD COLUMN IF NOT EXISTS fv_pct_cost   NUMERIC,
  ADD COLUMN IF NOT EXISTS floor_bps     NUMERIC,
  ADD COLUMN IF NOT EXISTS pik_bps       NUMERIC,
  ADD COLUMN IF NOT EXISTS maturity_date DATE,
  ADD COLUMN IF NOT EXISTS non_accrual   BOOLEAN;

ALTER TABLE facility_summary ADD COLUMN IF NOT EXISTS signal_codes TEXT[] NOT NULL DEFAULT '{}';

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'facility_summary_signal_codes_known') THEN
    ALTER TABLE facility_summary ADD CONSTRAINT facility_summary_signal_codes_known
      CHECK (signal_codes <@ ARRAY['NON_ACCRUAL','PIK_DIFFERS','FLOOR_DIFFERS','SPREAD_DIFFERS','MATURITY_DIFFERS','COST_BASIS_GAP','RATE_TYPE_DIFFERS']::TEXT[]);
  END IF;
END $$;
