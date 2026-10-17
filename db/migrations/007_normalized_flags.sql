-- Day 5: two columns on normalized_holdings that SPEC.md section 6 does not list.
-- non_accrual: the filer's own footnote says the loan is on non-accrual (pattern in config.yaml, per filer).
-- excluded_reason: why fair_value_pct_par is NULL for the row, one reason per row (first match wins).
ALTER TABLE normalized_holdings ADD COLUMN non_accrual BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE normalized_holdings ADD COLUMN excluded_reason TEXT;
