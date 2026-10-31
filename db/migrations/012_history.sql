-- v2 F3 (history and persistence). Additive. The prior quarter is history only: these tables are filled from normalized_holdings
-- (link_history.py) and from the curated facilities (compare.py). Nothing here is matcher output and nothing reads candidate pairs.
CREATE TABLE IF NOT EXISTS holding_history_links (
  holding_id        INT PRIMARY KEY REFERENCES normalized_holdings(holding_id),
  prior_holding_id  INT NOT NULL UNIQUE REFERENCES normalized_holdings(holding_id),   -- a prior holding links to at most one current holding
  link_rule         TEXT NOT NULL CHECK (link_rule IN ('EXACT_KEY', 'EXACT_MATURITY')),
  CHECK (holding_id <> prior_holding_id)
);

-- One row once link_history.py has run. Its presence is what "F3 is built" means: the API shows history null before it,
-- and NO_PRIOR for a facility without a facility_history row after it.
CREATE TABLE IF NOT EXISTS history_build (
  build_id          INT PRIMARY KEY CHECK (build_id = 1),
  prior_period_end  DATE NOT NULL,
  period_end_date   DATE NOT NULL,
  current_holdings  INT NOT NULL,
  linked            INT NOT NULL,
  built_at          TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS facility_history (
  facility_id            INT PRIMARY KEY REFERENCES canonical_facilities(facility_id),
  prior_period_end       DATE NOT NULL,
  prior_lender_count     INT  NOT NULL CHECK (prior_lender_count >= 2),
  prior_divergence_pts   NUMERIC NOT NULL,
  prior_divergence_flag  TEXT NOT NULL CHECK (prior_divergence_flag IN ('AGREEMENT', 'MILD', 'FLAGGED')),
  persistence            TEXT NOT NULL CHECK (persistence IN ('WIDENED', 'NARROWED', 'CLOSED', 'STABLE'))
);

-- Hand check of the within-BDC link, like blocking_recall_checks. NO_PRIOR is derived by absence from facility_history.
CREATE TABLE IF NOT EXISTS history_link_checks (
  check_id          SERIAL PRIMARY KEY,
  holding_id        INT NOT NULL REFERENCES normalized_holdings(holding_id),
  prior_holding_id  INT NOT NULL REFERENCES normalized_holdings(holding_id),
  label             TEXT NOT NULL CHECK (label IN ('MATCH', 'NO_MATCH', 'UNSURE')),
  labeled_by        TEXT NOT NULL,
  checked_at        TIMESTAMPTZ DEFAULT now(),
  UNIQUE (holding_id, prior_holding_id)
);
