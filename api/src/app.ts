import express, { NextFunction, Request, Response } from "express";
import type { Pool } from "pg";
import { ApiError, sendError } from "./errors";
import { registerFacilities } from "./facilities";
import { registerLabeling } from "./labeling";
import { registerReview } from "./review";

// Convention: NUMERIC values leave the API as strings, exactly as Postgres returns them.
// JSON numbers are doubles, which would lose digits on money values. Conversion happens at the UI edge.

export { ApiError };

export type AppOptions = {
  pool: Pool;
  enableLabeling: boolean; // ENABLE_LABELING, default false (no auth, so E11 and E12 are opt in)
  nodeEnv: string;
  measuredPeriodEnd: string; // MEASURED_PERIOD_END (YYYY-MM-DD), set once in .env and read by the pipeline and the API; E1 returns it
};

// Skeleton handler: the route exists in the CONTRACT.md endpoint index but is not built yet.
// CONTRACT.md names no 501 code, so NOT_IMPLEMENTED is used in the standard shape.
function notImplemented(id: string) {
  return (_req: Request, res: Response) => {
    sendError(res, 501, "NOT_IMPLEMENTED", `${id} is not implemented yet.`);
  };
}

export function createApp(opts: AppOptions): express.Express {
  const { pool } = opts;
  const app = express();

  // E1 to E5 (facilities.ts), E6 to E8 (review.ts)
  registerFacilities(app, pool, opts.measuredPeriodEnd);
  registerReview(app, pool);

  // E9 is Day 9 work (the held-out evaluation and the live fields).
  app.get("/api/metrics", notImplemented("E9"));

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
  app.use((_req: Request, res: Response) => {
    sendError(res, 404, "NOT_FOUND", "No such route.");
  });

  // Error middleware: ApiError keeps its status and code, anything else is a 500.
  app.use((err: unknown, _req: Request, res: Response, _next: NextFunction) => {
    if (err instanceof ApiError) {
      sendError(res, err.status, err.code, err.message);
      return;
    }
    if ((err as { type?: string })?.type === "entity.parse.failed") {
      sendError(res, 400, "BAD_REQUEST", "The request body is not valid JSON.");
      return;
    }
    console.error(err);
    sendError(res, 500, "INTERNAL_ERROR", "Unexpected server error.");
  });

  return app;
}
