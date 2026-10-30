import express, { Express, Request, Response } from "express";
import type { Pool } from "pg";

// E11 and E12 (CONTRACT.md). Mounted by createApp only when ENABLE_LABELING=true.
// E11 reads only label_samples, labeled_pairs, normalized_holdings and raw_holdings, and never selects a score,
// a status, a band, a phase or a draw order into the response. E12 writes labeled_pairs only.
// NUMERIC values leave as strings, like the rest of the API.

const LABELS = ["MATCH", "NO_MATCH", "UNSURE"];

function sendError(res: Response, status: number, code: string, message: string) {
  res.status(status).json({ error: { code, message } });
}

type HoldingRow = {
  rawName: string | null;
  instrumentType: string;
  maturityDate: string | null;
  spreadBps: string | null;
  industry: string | null;
  footnotes: string | null;
  borrowerNormalized: string;
};

async function holding(pool: Pool, id: number, pairIds: number[]) {
  const { rows } = await pool.query<HoldingRow>(
    `SELECT r.portfolio_company_raw AS "rawName",
            n.instrument_type_norm AS "instrumentType",
            to_char(n.maturity_date, 'YYYY-MM-DD') AS "maturityDate",
            n.spread_bps AS "spreadBps",
            n.industry AS "industry",
            n.footnotes AS "footnotes",
            n.borrower_normalized AS "borrowerNormalized"
       FROM normalized_holdings n
       JOIN raw_holdings r ON r.holding_id = n.holding_id
      WHERE n.holding_id = $1`,
    [id],
  );
  const h = rows[0];
  // Other holdings, in any ingested filing of the same period as the pair, with exactly this normalized borrower name.
  // Exact equality, no scoring. Rows of another quarter never appear as evidence.
  const names = await pool.query<{ name: string }>(
    `SELECT DISTINCT r.portfolio_company_raw AS name
       FROM normalized_holdings n
       JOIN raw_holdings r ON r.holding_id = n.holding_id
      WHERE n.borrower_normalized = $1
        AND n.holding_id <> ALL($2::int[])
        AND n.period_end_date = (SELECT period_end_date FROM normalized_holdings WHERE holding_id = $3)
        AND r.portfolio_company_raw IS NOT NULL
      ORDER BY 1`,
    [h.borrowerNormalized, pairIds, id],
  );
  return {
    holdingId: id,
    rawName: h.rawName,
    instrumentType: h.instrumentType,
    maturityDate: h.maturityDate,
    spreadBps: h.spreadBps,
    industry: h.industry,
    footnotes: h.footnotes,
    crossFilingNames: names.rows.map((r) => r.name),
  };
}

export function registerLabeling(app: Express, pool: Pool) {
  // E11 GET /api/label/next
  app.get("/api/label/next", async (_req: Request, res: Response) => {
    const next = await pool.query<{ sample_id: number; phase: string; holding_id_a: number; holding_id_b: number }>(
      `SELECT s.sample_id, s.phase, s.holding_id_a, s.holding_id_b
         FROM label_samples s
        WHERE NOT EXISTS (SELECT 1 FROM labeled_pairs l WHERE l.sample_id = s.sample_id)
        ORDER BY CASE s.phase WHEN 'TUNING' THEN 0 WHEN 'HELDOUT' THEN 1 WHEN 'OUTOFTIME' THEN 2 ELSE 3 END, s.draw_order, s.sample_id
        LIMIT 1`,
    );
    if (next.rows.length === 0) {
      res.status(204).end();
      return;
    }
    const s = next.rows[0];
    // progress counts the phase being served; the phase itself is not sent
    const progress = await pool.query<{ labeled: number; total: number }>(
      `SELECT COUNT(l.sample_id)::int AS labeled, COUNT(*)::int AS total
         FROM label_samples s
         LEFT JOIN labeled_pairs l ON l.sample_id = s.sample_id
        WHERE s.phase = $1`,
      [s.phase],
    );
    const ids = [s.holding_id_a, s.holding_id_b];
    res.json({
      sampleId: s.sample_id,
      progress: progress.rows[0],
      holdingA: await holding(pool, s.holding_id_a, ids),
      holdingB: await holding(pool, s.holding_id_b, ids),
    });
  });

  // E12 POST /api/label. The server derives everything except sampleId, label and labeledBy.
  app.post("/api/label", express.json(), async (req: Request, res: Response) => {
    const body = (req.body ?? {}) as Record<string, unknown>;
    const { sampleId, label, labeledBy } = body;
    if (typeof label !== "string" || !LABELS.includes(label)) {
      sendError(res, 400, "BAD_REQUEST", "label must be MATCH, NO_MATCH or UNSURE.");
      return;
    }
    if (typeof sampleId !== "number" || !Number.isInteger(sampleId) || sampleId < 1 || sampleId > 2147483647) {
      sendError(res, 400, "BAD_REQUEST", "sampleId must be a positive integer.");
      return;
    }
    if (typeof labeledBy !== "string" || labeledBy.trim() === "") {
      sendError(res, 400, "BAD_REQUEST", "labeledBy is required.");
      return;
    }
    const { rows } = await pool.query<{ sampleId: number; label: string; labeledAt: Date }>(
      `INSERT INTO labeled_pairs (sample_id, holding_id_a, holding_id_b, label, labeled_by, sampling_method, score_band)
       SELECT s.sample_id, s.holding_id_a, s.holding_id_b, $2, $3,
              CASE s.phase WHEN 'TUNING' THEN 'BLOCKED' WHEN 'HELDOUT' THEN 'STRATIFIED' WHEN 'OUTOFTIME' THEN 'STRATIFIED' END, s.score_band
         FROM label_samples s
        WHERE s.sample_id = $1
       ON CONFLICT (sample_id) DO UPDATE
          SET label = EXCLUDED.label, labeled_by = EXCLUDED.labeled_by, labeled_at = now()
       RETURNING sample_id AS "sampleId", label, labeled_at AS "labeledAt"`,
      [sampleId, label, labeledBy.trim()],
    );
    if (rows.length === 0) {
      sendError(res, 404, "NOT_FOUND", "No such sample.");
      return;
    }
    res.json({ sampleId: rows[0].sampleId, label: rows[0].label, labeledAt: rows[0].labeledAt.toISOString() });
  });
}
