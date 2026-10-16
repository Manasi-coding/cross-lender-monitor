-- Day 3: sha256 of the filing document that was loaded. Used by ingest to refuse a changed file on a rerun.
-- Not in SPEC.md section 6 as first written; SPEC.md section 6 raw_filings carries the same line.
ALTER TABLE raw_filings ADD COLUMN source_sha256 TEXT;
