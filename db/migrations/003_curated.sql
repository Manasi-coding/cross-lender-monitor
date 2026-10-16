-- CURATED LAYER (SPEC.md section 6). Rebuilt in full, in one transaction, by compare.py.
CREATE TABLE canonical_borrowers (
  canonical_borrower_id SERIAL PRIMARY KEY,
  canonical_name        TEXT NOT NULL,        -- exact normalized cluster name (SPEC 5 step 3)
  period_end_date       DATE NOT NULL,
  created_at            TIMESTAMPTZ DEFAULT now(),
  UNIQUE (canonical_name, period_end_date)
);

CREATE TABLE canonical_facilities (
  facility_id            SERIAL PRIMARY KEY,
  canonical_borrower_id  INT NOT NULL REFERENCES canonical_borrowers(canonical_borrower_id),
  period_end_date        DATE NOT NULL,
  instrument_type_norm   TEXT NOT NULL,
  reference_rate         TEXT,
  maturity_bucket        DATE                 -- earliest member maturity (default)
);

CREATE TABLE holding_facility_map (
  holding_id    INT PRIMARY KEY REFERENCES normalized_holdings(holding_id),   -- a holding is in at most one facility
  facility_id   INT NOT NULL REFERENCES canonical_facilities(facility_id)
  -- built from candidate_pairs where status IN ('AUTO','CONFIRMED') via clustering, never a separate source of truth
);

-- One row per holding in a facility: a snapshot of exactly what was compared.
-- Excluded holdings are kept and flagged.
CREATE TABLE facility_comparisons (
  facility_id         INT NOT NULL REFERENCES canonical_facilities(facility_id),
  holding_id          INT NOT NULL REFERENCES normalized_holdings(holding_id),
  period_end_date     DATE NOT NULL,
  bdc_cik             TEXT NOT NULL,
  bdc_name            TEXT NOT NULL,
  spread_bps_total    NUMERIC,                -- spread_bps + pik_bps
  principal           NUMERIC,
  fair_value_pct_par  NUMERIC,                -- NULL when excluded
  excluded_reason     TEXT,                   -- NULL | ZERO_OR_NULL_PRINCIPAL | NULL_FAIR_VALUE | NON_USD_PRINCIPAL | UNFUNDED_COMMITMENT
  source_url          TEXT NOT NULL,
  PRIMARY KEY (facility_id, holding_id)
);

-- One row per facility
CREATE TABLE facility_summary (
  facility_id      INT PRIMARY KEY REFERENCES canonical_facilities(facility_id),
  lender_count     INT NOT NULL CHECK (lender_count >= 2),   -- holdings with a usable mark
  excluded_count   INT NOT NULL,
  divergence_pts   NUMERIC NOT NULL,          -- max minus min fair_value_pct_par over included holdings
  divergence_flag  TEXT NOT NULL              -- AGREEMENT | MILD | FLAGGED (cutoffs in SPEC 12.8)
);

CREATE TABLE review_clusters (
  cluster_id       SERIAL PRIMARY KEY,
  period_end_date  DATE NOT NULL,
  reason           TEXT NOT NULL              -- SAME_BDC_COLLISION
);

CREATE TABLE review_cluster_members (
  cluster_id  INT NOT NULL REFERENCES review_clusters(cluster_id) ON DELETE CASCADE,
  holding_id  INT NOT NULL REFERENCES normalized_holdings(holding_id),
  PRIMARY KEY (cluster_id, holding_id)
);
