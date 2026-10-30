-- Draw records (Day 8 afternoon, after the freeze).
-- band_sizes.draw_seed: the seed the held-out draw used (sampling.heldout_seed). It is NULL only for a draw made before this
-- migration; the one live held-out draw is backfilled with 2 by hand and recorded in DECISIONS.md.
ALTER TABLE band_sizes ADD COLUMN draw_seed INT;

-- The out-of-time sample (phase OUTOFTIME in label_samples): pairs of the prior quarter, drawn after the freeze, by stored score.
-- band_sizes cannot hold these sizes (its primary key is the band alone and it holds the held-out sizes), so they get their own
-- table with the period, the seed and the matcher hash. One row per band; LOW has sample_size 0 when it is not sampled.
CREATE TABLE outoftime_band_sizes (
  score_band           TEXT PRIMARY KEY,      -- AUTO | REVIEW | JUST_BELOW | LOW
  band_size            INT NOT NULL,          -- frame size: candidate pairs of period_end_date in this band at draw time
  sample_size          INT NOT NULL,
  period_end_date      DATE NOT NULL,         -- the prior quarter, never the measured period
  draw_seed            INT NOT NULL,
  matcher_config_hash  TEXT NOT NULL,         -- equals matcher_freeze.matcher_config_hash at draw time
  drawn_at             TIMESTAMPTZ DEFAULT now()
);
