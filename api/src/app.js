import express from "express";

import { ApiError, sendError } from "./errors.js";
import { registerFacilities } from "./facilities.js";
import { registerLabeling } from "./labeling.js";
import { registerMetrics } from "./metrics.js";
import { registerReview } from "./review.js";

// Convention: NUMERIC values leave the API as strings, exactly as Postgres returns them.
// JSON numbers are doubles, which would lose digits on money values. Conversion happens at the UI edge.

export { ApiError };

export function createApp(opts) {
  const { pool } = opts;
  const app = express();

  // Guard the entire API before route handlers or body parsers can do any work.
  app.use("/api", (req, res, next) => {
    if (opts.readOnly && req.method !== "GET" && req.method !== "HEAD") {
      sendError(res, 403, "BAD_REQUEST", "This is a read-only demo; decisions are disabled");
      return;
    }
    next();
  });

  // E1 to E5 (facilities.js), E6 to E8 (review.js)
  registerFacilities(app, pool, opts.measuredPeriodEnd);
  registerReview(app, pool, opts.measuredPeriodEnd);

  // E9 (metrics.js)
  registerMetrics(app, pool, opts.measuredPeriodEnd);

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

  // E11, E12: mounted only when ENABLE_LABELING=true, otherwise the paths are unknown and return 404.
  if (opts.enableLabeling) {
    registerLabeling(app, pool);
  }

  // Unknown id or route not mounted: 404 in the standard shape.
  app.use((_req, res) => {
    sendError(res, 404, "NOT_FOUND", "No such route.");
  });

  // Error middleware: ApiError keeps its status and code, anything else is a 500.
  app.use((err, _req, res, _next) => {
    if (err instanceof ApiError) {
      sendError(res, err.status, err.code, err.message);
      return;
    }
    if ((err)?.type === "entity.parse.failed") {
      sendError(res, 400, "BAD_REQUEST", "The request body is not valid JSON.");
      return;
    }
    console.error(err);
    sendError(res, 500, "INTERNAL_ERROR", "Unexpected server error.");
  });

  return app;
}
