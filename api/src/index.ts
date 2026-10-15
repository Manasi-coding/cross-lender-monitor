import express from "express";
import { Pool } from "pg";

// Convention: NUMERIC values leave the API as strings, exactly as Postgres returns them.
// JSON numbers are doubles, which would lose digits on money values. Conversion happens at the UI edge.

const pool = new Pool({ connectionString: process.env.DATABASE_URL });
const app = express();

// E10 GET /api/filings (CONTRACT.md). Sort: periodEnd descending, bdcName ascending.
app.get("/api/filings", async (_req, res) => {
  const { rows } = await pool.query(
    `SELECT f.bdc_name AS "bdcName",
            f.cik AS "cik",
            f.form_type AS "formType",
            to_char(f.period_end_date, 'YYYY-MM-DD') AS "periodEnd",
            COUNT(h.holding_id)::int AS "holdingsCount",
            f.source_url AS "sourceUrl"
       FROM raw_filings f
       LEFT JOIN raw_holdings h ON h.filing_id = f.filing_id
      GROUP BY f.filing_id
      ORDER BY f.period_end_date DESC, f.bdc_name ASC`,
  );
  res.json(rows);
});

// TODO(Day 7): temporary dev route, not part of CONTRACT.md. Delete it on Day 7 together with
// web/src/DevHoldings.tsx. Mounted only when NODE_ENV=development.
if (process.env.NODE_ENV === "development") {
  app.get("/api/_dev/holdings", async (_req, res) => {
    const { rows } = await pool.query(
      `SELECT portfolio_company_raw AS name,
              principal_raw AS principal,
              cost_raw AS cost,
              fair_value_raw AS fair_value,
              source_url
         FROM raw_holdings
        ORDER BY holding_id`,
    );
    res.json(rows);
  });
}

const port = Number(process.env.PORT ?? 3000);
app.listen(port, () => {
  console.log(`api listening on ${port}`);
});
