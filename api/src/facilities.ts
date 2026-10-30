import type { Express, Request, Response } from "express";
import type { Pool } from "pg";
import { ApiError, likePattern, parseId } from "./errors";

// E1 to E5 (CONTRACT.md). Read only, parameterized SQL, no config file. NUMERIC values leave as strings, as Postgres returns them.
// [v2] fields built on Day 7: E1 flaggedExposureUsd, and E4 divergencePts, divergenceFlag, exposureUsd with the flag and sort parameters.
// [v2] fields not built yet and left out: E4 signalCount and persistence, E5 exposureUsd, signals, dossier row fields and history.

const FLAGS = ["AGREEMENT", "MILD", "FLAGGED"];
const SORTS = ["borrower", "exposure"];

export function registerFacilities(app: Express, pool: Pool, measuredPeriodEnd: string) {
  // E1 GET /api/overview
  app.get("/api/overview", async (_req: Request, res: Response) => {
    const [filings, facilities, pending, split, exposure] = await Promise.all([
      pool.query(`SELECT COUNT(DISTINCT cik)::int AS "bdcCount", COUNT(DISTINCT period_end_date)::int AS "quarterCount" FROM raw_filings`),
      pool.query(`SELECT COUNT(*)::int AS n FROM canonical_facilities`),
      // only the measured period: pairs from another quarter that were matched out of time are not part of the review queue
      pool.query(
        `SELECT ((SELECT COUNT(*) FROM candidate_pairs c
                    JOIN normalized_holdings a ON a.holding_id = c.holding_id_a
                    JOIN normalized_holdings b ON b.holding_id = c.holding_id_b
                   WHERE c.status = 'REVIEW' AND a.period_end_date = $1 AND b.period_end_date = $1)
                + (SELECT COUNT(*) FROM review_clusters WHERE period_end_date = $1))::int AS n`,
        [measuredPeriodEnd],
      ),
      pool.query(`SELECT divergence_flag AS flag, COUNT(*)::int AS n FROM facility_summary GROUP BY divergence_flag`),
      pool.query(`SELECT COALESCE(SUM(exposure_usd) FILTER (WHERE divergence_flag = 'FLAGGED'), 0) AS total FROM facility_summary`),
    ]);
    const counts = new Map<string, number>(split.rows.map((r) => [r.flag as string, r.n as number]));
    const hasSummary = split.rows.length > 0;
    res.json({
      bdcCount: filings.rows[0].bdcCount,
      quarterCount: filings.rows[0].quarterCount,
      measuredPeriodEnd,
      facilityCount: facilities.rows[0].n,
      pendingReviewCount: pending.rows[0].n,
      divergenceSplit: hasSummary
        ? { agreement: counts.get("AGREEMENT") ?? 0, mild: counts.get("MILD") ?? 0, flagged: counts.get("FLAGGED") ?? 0 }
        : null,
      flaggedExposureUsd: hasSummary ? exposure.rows[0].total : null, // [v2]
    });
  });

  const borrowerCounts = `
    (SELECT COUNT(DISTINCT c.bdc_cik) FROM canonical_facilities f JOIN facility_comparisons c ON c.facility_id = f.facility_id
      WHERE f.canonical_borrower_id = b.canonical_borrower_id AND c.fair_value_pct_par IS NOT NULL)::int AS "lenderCount",
    (SELECT COUNT(*) FROM canonical_facilities f WHERE f.canonical_borrower_id = b.canonical_borrower_id)::int AS "facilityCount"`;

  // E2 GET /api/borrowers?search=
  app.get("/api/borrowers", async (req: Request, res: Response) => {
    const { rows } = await pool.query(
      `SELECT b.canonical_borrower_id AS "canonicalBorrowerId", b.canonical_name AS "canonicalName",
              to_char(b.period_end_date, 'YYYY-MM-DD') AS "periodEnd", ${borrowerCounts}
         FROM canonical_borrowers b
        WHERE ($1::text IS NULL OR b.canonical_name ILIKE $1 ESCAPE '\\')
        ORDER BY b.canonical_name COLLATE "C" ASC, b.period_end_date DESC, b.canonical_borrower_id ASC`,
      [likePattern(req.query.search)],
    );
    res.json(rows);
  });

  // E3 GET /api/borrowers/:id/facilities
  app.get("/api/borrowers/:id/facilities", async (req: Request, res: Response) => {
    const id = parseId(req.params.id as string, "borrower id");
    const head = await pool.query(
      `SELECT b.canonical_borrower_id AS "canonicalBorrowerId", b.canonical_name AS "canonicalName",
              to_char(b.period_end_date, 'YYYY-MM-DD') AS "periodEnd", ${borrowerCounts}
         FROM canonical_borrowers b WHERE b.canonical_borrower_id = $1`,
      [id],
    );
    if (head.rows.length === 0) throw new ApiError(404, "NOT_FOUND", "No such borrower.");
    const { rows } = await pool.query(
      `SELECT f.facility_id AS "facilityId", f.instrument_type_norm AS "instrumentType", f.reference_rate AS "referenceRate",
              to_char(f.maturity_bucket, 'YYYY-MM-DD') AS "maturityBucket", s.lender_count AS "lenderCount"
         FROM canonical_facilities f JOIN facility_summary s ON s.facility_id = f.facility_id
        WHERE f.canonical_borrower_id = $1
        ORDER BY f.instrument_type_norm COLLATE "C" ASC, f.maturity_bucket ASC NULLS LAST, f.facility_id ASC`,
      [id],
    );
    res.json({ ...head.rows[0], facilities: rows });
  });

  // E4 GET /api/facilities?search=&flag=&sort=
  app.get("/api/facilities", async (req: Request, res: Response) => {
    const flag = req.query.flag;
    const sort = req.query.sort ?? "borrower";
    if (flag !== undefined && (typeof flag !== "string" || !FLAGS.includes(flag))) {
      throw new ApiError(400, "BAD_REQUEST", "flag must be AGREEMENT, MILD or FLAGGED.");
    }
    if (typeof sort !== "string" || !SORTS.includes(sort)) {
      throw new ApiError(400, "BAD_REQUEST", "sort must be borrower or exposure.");
    }
    const order =
      sort === "exposure"
        ? `s.exposure_usd DESC, s.divergence_pts DESC, f.facility_id ASC`
        : `b.canonical_name COLLATE "C" ASC, f.instrument_type_norm COLLATE "C" ASC, f.period_end_date DESC, f.facility_id ASC`;
    const { rows } = await pool.query(
      `SELECT f.facility_id AS "facilityId", b.canonical_name AS "borrowerName",
              to_char(f.period_end_date, 'YYYY-MM-DD') AS "periodEnd", f.instrument_type_norm AS "instrumentType",
              f.reference_rate AS "referenceRate",
              (SELECT MIN(c.spread_bps_total) FROM facility_comparisons c WHERE c.facility_id = f.facility_id AND c.fair_value_pct_par IS NOT NULL) AS "spreadMin",
              (SELECT MAX(c.spread_bps_total) FROM facility_comparisons c WHERE c.facility_id = f.facility_id AND c.fair_value_pct_par IS NOT NULL) AS "spreadMax",
              to_char(f.maturity_bucket, 'YYYY-MM-DD') AS "maturityBucket", s.lender_count AS "lenderCount",
              s.divergence_pts AS "divergencePts", s.divergence_flag AS "divergenceFlag", s.exposure_usd AS "exposureUsd"
         FROM canonical_facilities f
         JOIN canonical_borrowers b ON b.canonical_borrower_id = f.canonical_borrower_id
         JOIN facility_summary s ON s.facility_id = f.facility_id
        WHERE ($1::text IS NULL OR b.canonical_name ILIKE $1 ESCAPE '\\')
          AND ($2::text IS NULL OR s.divergence_flag = $2)
        ORDER BY ${order}`,
      [likePattern(req.query.search), flag ?? null],
    );
    res.json(
      rows.map(({ spreadMin, spreadMax, ...r }) => ({
        facilityId: r.facilityId,
        borrowerName: r.borrowerName,
        periodEnd: r.periodEnd,
        instrumentType: r.instrumentType,
        referenceRate: r.referenceRate,
        spreadBps: { min: spreadMin, max: spreadMax },
        maturityBucket: r.maturityBucket,
        lenderCount: r.lenderCount,
        divergencePts: r.divergencePts,
        divergenceFlag: r.divergenceFlag,
        exposureUsd: r.exposureUsd,
      })),
    );
  });

  // E5 GET /api/facilities/:id/comparison
  app.get("/api/facilities/:id/comparison", async (req: Request, res: Response) => {
    const id = parseId(req.params.id as string, "facility id");
    const head = await pool.query(
      `SELECT f.facility_id AS "facilityId", b.canonical_name AS "borrowerName",
              to_char(f.period_end_date, 'YYYY-MM-DD') AS "periodEnd", f.instrument_type_norm AS "instrumentType",
              f.reference_rate AS "referenceRate", to_char(f.maturity_bucket, 'YYYY-MM-DD') AS "maturityBucket",
              s.excluded_count AS "excludedCount", s.divergence_pts AS "divergencePts", s.divergence_flag AS "divergenceFlag"
         FROM canonical_facilities f
         JOIN canonical_borrowers b ON b.canonical_borrower_id = f.canonical_borrower_id
         JOIN facility_summary s ON s.facility_id = f.facility_id
        WHERE f.facility_id = $1`,
      [id],
    );
    if (head.rows.length === 0) throw new ApiError(404, "NOT_FOUND", "No such facility.");
    const { rows } = await pool.query(
      `SELECT c.bdc_name AS "bdcName", c.spread_bps_total AS "spreadBps", c.fair_value_pct_par AS "fairValuePctPar",
              c.principal AS "principal", c.source_url AS "sourceUrl"
         FROM facility_comparisons c
        WHERE c.facility_id = $1 AND c.fair_value_pct_par IS NOT NULL
        ORDER BY c.bdc_name COLLATE "C" ASC, c.holding_id ASC`,
      [id],
    );
    // every facility has at least 2 included rows; fewer means stored data broke an invariant
    if (rows.length < 2) throw new ApiError(500, "DATA_INTEGRITY", "A facility has fewer than 2 lenders with a usable mark.");
    const h = head.rows[0];
    res.json({
      facilityId: h.facilityId,
      borrowerName: h.borrowerName,
      periodEnd: h.periodEnd,
      instrumentType: h.instrumentType,
      referenceRate: h.referenceRate,
      maturityBucket: h.maturityBucket,
      rows,
      excludedCount: h.excludedCount,
      divergencePts: h.divergencePts,
      divergenceFlag: h.divergenceFlag,
    });
  });
}
