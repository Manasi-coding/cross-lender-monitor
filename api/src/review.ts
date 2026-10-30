import type { Express, Request, Response } from "express";
import type { Pool } from "pg";
import { ApiError, parseId } from "./errors";

// E6, E7, E8 (CONTRACT.md). E7 and E8 update candidate_pairs.status and updated_at only. They change no curated table,
// labeled_pairs or metric: the effect appears after the next compare.py run.

const DATE = (col: string) => `to_char(${col}, 'YYYY-MM-DD')`;

export function registerReview(app: Express, pool: Pool, measuredPeriodEnd: string) {
  // E6 GET /api/review-queue: clusters first, then REVIEW pairs by score descending, then holdingIdA, holdingIdB.
  // Only the measured period (MEASURED_PERIOD_END): a pair or cluster of another quarter is neither listed nor counted.
  app.get("/api/review-queue", async (_req: Request, res: Response) => {
    const [clusters, members, edges, pairs] = await Promise.all([
      pool.query(
        `SELECT cluster_id AS "clusterId", ${DATE("period_end_date")} AS "periodEnd", reason FROM review_clusters WHERE period_end_date = $1 ORDER BY cluster_id`,
        [measuredPeriodEnd],
      ),
      pool.query(
        `SELECT m.cluster_id AS "clusterId", n.holding_id AS "holdingId", f.bdc_name AS "bdcName", h.portfolio_company_raw AS "rawName",
                n.instrument_type_norm AS "instrumentType", ${DATE("n.maturity_date")} AS "maturityDate",
                n.spread_bps AS "spreadBps", n.source_url AS "sourceUrl"
           FROM review_cluster_members m
           JOIN review_clusters rc ON rc.cluster_id = m.cluster_id AND rc.period_end_date = $1
           JOIN normalized_holdings n ON n.holding_id = m.holding_id
           JOIN raw_holdings h ON h.holding_id = n.holding_id
           JOIN raw_filings f ON f.filing_id = h.filing_id
          ORDER BY m.cluster_id, n.holding_id`,
        [measuredPeriodEnd],
      ),
      // the AUTO or CONFIRMED edges that formed each cluster: candidate pairs with both holdings in the cluster
      pool.query(
        `SELECT m1.cluster_id AS "clusterId", c.holding_id_a AS "holdingIdA", c.holding_id_b AS "holdingIdB", c.score AS "score", c.status AS "status"
           FROM review_cluster_members m1
           JOIN review_clusters rc ON rc.cluster_id = m1.cluster_id AND rc.period_end_date = $1
           JOIN review_cluster_members m2 ON m2.cluster_id = m1.cluster_id AND m2.holding_id > m1.holding_id
           JOIN candidate_pairs c ON c.holding_id_a = m1.holding_id AND c.holding_id_b = m2.holding_id
          WHERE c.status IN ('AUTO', 'CONFIRMED')
          ORDER BY m1.cluster_id, c.score DESC, c.holding_id_a, c.holding_id_b`,
        [measuredPeriodEnd],
      ),
      pool.query(
        `SELECT ${DATE("a.period_end_date")} AS "periodEnd", c.holding_id_a AS "holdingIdA", c.holding_id_b AS "holdingIdB",
                ra.portfolio_company_raw AS "rawNameA", rb.portfolio_company_raw AS "rawNameB", c.score AS "score",
                a.instrument_type_norm AS "instrumentType", ${DATE("a.maturity_date")} AS "maturityDateA", ${DATE("b.maturity_date")} AS "maturityDateB",
                a.spread_bps AS "spreadBpsA", b.spread_bps AS "spreadBpsB", a.source_url AS "sourceUrlA", b.source_url AS "sourceUrlB"
           FROM candidate_pairs c
           JOIN normalized_holdings a ON a.holding_id = c.holding_id_a
           JOIN normalized_holdings b ON b.holding_id = c.holding_id_b
           JOIN raw_holdings ra ON ra.holding_id = a.holding_id
           JOIN raw_holdings rb ON rb.holding_id = b.holding_id
          WHERE c.status = 'REVIEW' AND a.period_end_date = $1 AND b.period_end_date = $1
          ORDER BY c.score DESC, c.holding_id_a, c.holding_id_b`,
        [measuredPeriodEnd],
      ),
    ]);
    const byCluster = <T extends { clusterId: number }>(rows: T[]) => {
      const m = new Map<number, Omit<T, "clusterId">[]>();
      for (const { clusterId, ...rest } of rows) {
        if (!m.has(clusterId)) m.set(clusterId, []);
        m.get(clusterId)!.push(rest);
      }
      return m;
    };
    const holdings = byCluster(members.rows);
    const clusterPairs = byCluster(edges.rows);
    res.json([
      ...clusters.rows.map((c) => ({
        type: "cluster",
        clusterId: c.clusterId,
        periodEnd: c.periodEnd,
        reason: c.reason,
        holdings: holdings.get(c.clusterId) ?? [],
        pairs: clusterPairs.get(c.clusterId) ?? [],
      })),
      ...pairs.rows.map((p) => ({ type: "pair", ...p })),
    ]);
  });

  // Path ids are accepted in either order; the server orders them so holdingIdA < holdingIdB.
  async function transition(req: Request, res: Response, to: "CONFIRMED" | "REJECTED", from: string[]) {
    const x = parseId(req.params.idA as string, "holding id");
    const y = parseId(req.params.idB as string, "holding id");
    const [a, b] = x < y ? [x, y] : [y, x];
    // one statement: the status check and the update cannot be separated by another request
    const done = await pool.query(
      `UPDATE candidate_pairs SET status = $3, updated_at = now()
        WHERE holding_id_a = $1 AND holding_id_b = $2 AND status = ANY($4::text[])
        RETURNING holding_id_a AS "holdingIdA", holding_id_b AS "holdingIdB", status`,
      [a, b, to, from],
    );
    if (done.rows.length === 1) {
      res.json(done.rows[0]);
      return;
    }
    const exists = await pool.query(`SELECT status FROM candidate_pairs WHERE holding_id_a = $1 AND holding_id_b = $2`, [a, b]);
    if (exists.rows.length === 0) throw new ApiError(404, "NOT_FOUND", "No such pair.");
    throw new ApiError(409, "CONFLICT", `A pair with status ${exists.rows[0].status} cannot become ${to}.`);
  }

  // E7 allowed only from REVIEW. E8 allowed from AUTO, REVIEW or CONFIRMED. Anything else is 409.
  app.post("/api/review-queue/:idA/:idB/confirm", (req, res) => transition(req, res, "CONFIRMED", ["REVIEW"]));
  app.post("/api/review-queue/:idA/:idB/reject", (req, res) => transition(req, res, "REJECTED", ["AUTO", "REVIEW", "CONFIRMED"]));
}
