-- Which rung of the currency evidence ladder set principal_currency (pipeline/currency.py).
-- NULL where the principal unit tag decided, which is every row of every filing except HPS 2026-03-31.
ALTER TABLE normalized_holdings ADD COLUMN currency_source TEXT;   -- html_symbol | reference_code | period_link | unknown
