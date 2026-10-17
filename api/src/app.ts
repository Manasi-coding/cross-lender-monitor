import express, { NextFunction, Request, Response } from "express";
import type { Pool } from "pg";
import { registerLabeling } from "./labeling";

// Convention: NUMERIC values leave the API as strings, exactly as Postgres returns them.
// JSON numbers are doubles, which would lose digits on money values. Conversion happens at the UI edge.

export type AppOptions = {
  pool: Pool;
  enableLabeling: boolean; // ENABLE_LABELING, default false (no auth, so E11 and E12 are opt in)
  nodeEnv: string;
};

// Error shape from CONTRACT.md: an HTTP status plus { error: { code, message } }.
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

function sendError(res: Response, status: number, code: string, message: string) {
  res.status(status).json({ error: { code, message } });
}

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

  // E1
  app.get("/api/overview", notImplemented("E1"));
  // E2, E3
  app.get("/api/borrowers", notImplemented("E2"));
  app.get("/api/borrowers/:id/facilities", notImplemented("E3"));
  // E4, E5
  app.get("/api/facilities", notImplemented("E4"));
  app.get("/api/facilities/:id/comparison", notImplemented("E5"));
  // E6, E7, E8
  app.get("/api/review-queue", notImplemented("E6"));
  app.post("/api/review-queue/:idA/:idB/confirm", notImplemented("E7"));
  app.post("/api/review-queue/:idA/:idB/reject", notImplemented("E8"));
  // E9
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

  // TODO(Day 7): temporary dev route, not part of CONTRACT.md. Delete it on Day 7 together with
  // web/src/DevHoldings.tsx. Mounted only when NODE_ENV=development.
  if (opts.nodeEnv === "development") {
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
