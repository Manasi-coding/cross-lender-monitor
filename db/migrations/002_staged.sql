-- STAGED LAYER (SPEC.md section 6)
CREATE TABLE normalized_holdings (
  holding_id            INT PRIMARY KEY REFERENCES raw_holdings(holding_id),
  bdc_cik               TEXT NOT NULL,
  period_end_date       DATE NOT NULL,
  borrower_normalized   TEXT NOT NULL,
  industry              TEXT,               -- carried through: used as INDEPENDENT labeling evidence (SPEC 12), not matcher input
  instrument_type_norm  TEXT NOT NULL,
  reference_rate         TEXT,
  spread_bps             NUMERIC,
  floor_bps              NUMERIC,
  pik_bps                NUMERIC DEFAULT 0,
  maturity_date          DATE,
  principal              NUMERIC,
  principal_currency     TEXT,
  cost                   NUMERIC,
  fair_value             NUMERIC,
  fair_value_pct_par     NUMERIC,           -- NULL if principal IS NULL OR principal = 0 OR principal_currency <> 'USD' - guarded, never divide by zero
  footnotes              TEXT,              -- independent labeling evidence
  source_url             TEXT NOT NULL
);

CREATE TABLE blocking_keys (
  holding_id   INT REFERENCES normalized_holdings(holding_id),
  block_key    TEXT NOT NULL
);

-- CANDIDATE PAIRS: every holding-pair the matcher scored, independent of final facility assignment.
-- Store EVERY scored pair, including below 0.80 (status NO_MATCH). The CHECK enforces one canonical
-- ordering so a pair is never duplicated in both directions.
CREATE TABLE candidate_pairs (
  holding_id_a  INT REFERENCES normalized_holdings(holding_id),
  holding_id_b  INT REFERENCES normalized_holdings(holding_id),
  score         NUMERIC NOT NULL,
  status        TEXT NOT NULL,     -- AUTO | REVIEW | NO_MATCH | CONFIRMED | REJECTED
  updated_at    TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (holding_id_a, holding_id_b),
  CHECK (holding_id_a < holding_id_b)
);
