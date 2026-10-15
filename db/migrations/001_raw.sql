-- RAW LAYER (SPEC.md section 6). Values are kept as parsed, as text.
CREATE TABLE raw_filings (
  filing_id        SERIAL PRIMARY KEY,
  cik               TEXT NOT NULL,
  bdc_name          TEXT NOT NULL,
  form_type         TEXT NOT NULL,
  period_end_date   DATE NOT NULL,
  filing_date       DATE NOT NULL,
  accession_number  TEXT NOT NULL UNIQUE,
  source_url        TEXT NOT NULL,
  ingested_at       TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE raw_holdings (
  holding_id             SERIAL PRIMARY KEY,
  filing_id              INT REFERENCES raw_filings(filing_id),
  portfolio_company_raw  TEXT,
  industry_raw           TEXT,
  instrument_type_raw    TEXT,
  interest_rate_raw      TEXT,
  maturity_date_raw      TEXT,
  principal_raw          TEXT,
  principal_unit_raw     TEXT,   -- the unit tag on the principal fact, as parsed (for example u_EUR, u_USD)
  cost_raw               TEXT,
  fair_value_raw         TEXT,
  footnotes_raw          TEXT,
  row_order              INT,
  source_url             TEXT NOT NULL
);
