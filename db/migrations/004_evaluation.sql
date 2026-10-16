-- EVALUATION TABLES (SPEC.md section 6)
-- Both sampling phases draw only candidate pairs from the measured period (MEASURED_PERIOD_END).

-- Singleton: the current matcher freeze. Written by `config --freeze`, deleted by `config --unfreeze`.
CREATE TABLE matcher_freeze (
  freeze_id            INT PRIMARY KEY DEFAULT 1 CHECK (freeze_id = 1),
  matcher_config_hash  TEXT NOT NULL,
  git_sha              TEXT,
  frozen_at            TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE label_samples (
  sample_id     SERIAL PRIMARY KEY,
  holding_id_a  INT NOT NULL REFERENCES normalized_holdings(holding_id),
  holding_id_b  INT NOT NULL REFERENCES normalized_holdings(holding_id),
  phase         TEXT NOT NULL,                -- TUNING | HELDOUT
  score_band    TEXT,                         -- AUTO | REVIEW | JUST_BELOW | LOW; HELDOUT only
  draw_order    INT NOT NULL,                 -- random permutation; E11 serves in this order so order leaks nothing
  drawn_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE (holding_id_a, holding_id_b, phase),
  CHECK (holding_id_a < holding_id_b)
);

CREATE TABLE band_sizes (
  score_band           TEXT PRIMARY KEY,      -- AUTO | REVIEW | JUST_BELOW | LOW
  band_size            INT NOT NULL,          -- sampling frame size in this band at draw time (the N_b in SPEC 12.6)
  sample_size          INT NOT NULL,
  matcher_config_hash  TEXT NOT NULL,         -- equals matcher_freeze.matcher_config_hash at draw time
  drawn_at             TIMESTAMPTZ DEFAULT now()
);

-- GROUND TRUTH: kept separate from candidate_pairs and UI actions. Never merge these two tables
-- or use one to populate the other.
CREATE TABLE labeled_pairs (
  pair_id          SERIAL PRIMARY KEY,
  sample_id        INT NOT NULL UNIQUE REFERENCES label_samples(sample_id),
  holding_id_a     INT NOT NULL,
  holding_id_b     INT NOT NULL,
  label            TEXT NOT NULL,          -- MATCH | NO_MATCH | UNSURE
  labeled_by       TEXT NOT NULL,
  labeled_at       TIMESTAMPTZ DEFAULT now(),
  sampling_method  TEXT NOT NULL,          -- BLOCKED (tuning) | STRATIFIED (held-out)
  score_band       TEXT                    -- copied from label_samples for held-out rows, see SPEC 12.6
);

CREATE TABLE blocking_recall_checks (
  check_id                SERIAL PRIMARY KEY,
  holding_id              INT NOT NULL REFERENCES normalized_holdings(holding_id),  -- picked at random, independent of blocking
  counterpart_holding_id  INT NOT NULL REFERENCES normalized_holdings(holding_id),  -- found by hand in another BDC's schedule
  found_by_blocking       BOOLEAN NOT NULL,                                         -- did blocking put both in one block
  checked_at              TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE metric_results (
  metric_id            SERIAL PRIMARY KEY,
  computed_at          TIMESTAMPTZ DEFAULT now(),
  matcher_config_hash  TEXT NOT NULL,
  payload              JSONB NOT NULL         -- every label-derived E9 field; sensitivityTable and coverage are computed live by the API
);
