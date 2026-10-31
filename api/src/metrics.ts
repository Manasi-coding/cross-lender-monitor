import type { Express, Request, Response } from "express";
import type { Pool } from "pg";

// E9 GET /api/metrics (CONTRACT.md). Every label-derived field comes from the newest metric_results row and is null until
// evaluate.py has run. sensitivityTable and coverage are computed live from the curated tables. Nothing here reads
// candidate_pairs, labeled_pairs or label_samples, so review-queue clicks and labels cannot move a number on their own.
// [v2] additions: Range.unsureExcluded, bands[].counts and labeledInFull, and the separate outOfTime object.

const LABEL_FIELDS = [
  "precisionAutoOnly",
  "precisionReviewBand",
  "precisionIfReviewAutoAccepted",
  "recallAutoOnly",
  "recallIfReviewAutoAccepted",
  "blockingRecall",
  "bands",
  "unsureCount",
  "heldOutCount",
  "outOfTime",
] as const;

const THRESHOLDS = [1, 2, 5];
const SIGNALS = ["NON_ACCRUAL", "PIK_DIFFERS", "FLOOR_DIFFERS", "SPREAD_DIFFERS", "MATURITY_DIFFERS", "COST_BASIS_GAP", "RATE_TYPE_DIFFERS"];
// Dossier fields reported in fieldCoverage. nonAccrual is a flag with no "not parsed" state, so it is not listed.
const FIELDS: [string, string][] = [
  ["costPctPar", "cost_pct_par"],
  ["fvPctCost", "fv_pct_cost"],
  ["spreadBps", "spread_bps_total"],
  ["floorBps", "floor_bps"],
  ["pikBps", "pik_bps"],
  ["maturityDate", "maturity_date"],
];

// 95% Wilson interval, the same formula as evaluate.py (z = 1.96), for the hand check of the history link.
function wilson(k: number, n: number) {
  if (n === 0) return null;
  const z = 1.96;
  const p = k / n;
  const d = 1 + (z * z) / n;
  const c = (p + (z * z) / (2 * n)) / d;
  const h = (z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n))) / d;
  const r = (x: number) => Math.round(x * 1e6) / 1e6;
  return { value: r(p), low: r(Math.max(0, c - h)), high: r(Math.min(1, c + h)), n };
}

async function historyLinks(pool: Pool) {
  const built = await pool.query(`SELECT to_char(prior_period_end, 'YYYY-MM-DD') AS d FROM history_build`);
  if (built.rows.length === 0) return null;
  const [linked, checks] = await Promise.all([
    pool.query(
      `SELECT COUNT(*)::int AS n, COUNT(l.holding_id)::int AS k FROM facility_comparisons c
         LEFT JOIN holding_history_links l ON l.holding_id = c.holding_id WHERE c.fair_value_pct_par IS NOT NULL`,
    ),
    pool.query(`SELECT label, COUNT(*)::int AS n FROM history_link_checks GROUP BY label`),
  ]);
  const c = Object.fromEntries(checks.rows.map((r) => [r.label, r.n])) as Record<string, number>;
  const [m, no, u] = [c.MATCH ?? 0, c.NO_MATCH ?? 0, c.UNSURE ?? 0];
  const precision = m + no + u === 0 ? null : { unsureAsNoMatch: wilson(m, m + no + u), unsureAsMatch: wilson(m + u, m + no + u), unsureExcluded: wilson(m, m + no) };
  return { priorPeriodEnd: built.rows[0].d, linkedShare: share(linked.rows[0].k, linked.rows[0].n), precision };
}

const share = (k: number, n: number) => (n === 0 ? null : Math.round((k / n) * 1e6) / 1e6);

// Share of FLAGGED facilities that carry each signal against the share of AGREEMENT facilities, with both n. Descriptive only.
async function evidenceLift(pool: Pool) {
  const { rows } = await pool.query(
    `SELECT s.divergence_flag AS flag, COUNT(*)::int AS n, u.code, COUNT(*) FILTER (WHERE u.code = ANY(s.signal_codes))::int AS k
       FROM facility_summary s CROSS JOIN unnest($1::text[]) AS u(code)
      WHERE s.divergence_flag IN ('FLAGGED', 'AGREEMENT') GROUP BY s.divergence_flag, u.code`,
    [SIGNALS],
  );
  if (rows.length === 0) return null;
  const at = (flag: string, code: string) => rows.find((r) => r.flag === flag && r.code === code) ?? { n: 0, k: 0 };
  return SIGNALS.map((code) => {
    const f = at("FLAGGED", code);
    const a = at("AGREEMENT", code);
    return { code, flaggedShare: share(f.k, f.n), flaggedN: f.n, agreementShare: share(a.k, a.n), agreementN: a.n };
  });
}

async function unexplained(pool: Pool) {
  const { rows } = await pool.query(
    `SELECT COUNT(*)::int AS n, COUNT(*) FILTER (WHERE cardinality(signal_codes) = 0)::int AS k FROM facility_summary WHERE divergence_flag = 'FLAGGED'`,
  );
  const { n, k } = rows[0];
  return n === 0 ? null : { share: share(k, n), withoutSignal: k, flaggedN: n };
}

// For each field and BDC, the share of compared holdings (those with a mark) where the field was parsed.
async function fieldCoverage(pool: Pool) {
  const parts = FIELDS.map(([name, col]) => `SELECT '${name}' AS field, bdc_name, COUNT(*)::int AS n, COUNT(${col})::int AS k FROM facility_comparisons WHERE fair_value_pct_par IS NOT NULL GROUP BY bdc_name`);
  const { rows } = await pool.query(parts.join(" UNION ALL ") + ` ORDER BY 2, 1`);
  if (rows.length === 0) return null;
  const order = FIELDS.map(([name]) => name);
  return rows
    .sort((a, b) => (a.bdc_name < b.bdc_name ? -1 : a.bdc_name > b.bdc_name ? 1 : order.indexOf(a.field) - order.indexOf(b.field)))
    .map((r) => ({ field: r.field, bdcName: r.bdc_name, parsedShare: share(r.k, r.n), n: r.n }));
}

export function registerMetrics(app: Express, pool: Pool, measuredPeriodEnd: string) {
  app.get("/api/metrics", async (_req: Request, res: Response) => {
    const latest = await pool.query(`SELECT payload FROM metric_results ORDER BY metric_id DESC LIMIT 1`);
    const payload: Record<string, unknown> | null = latest.rows[0]?.payload ?? null;
    const [summary, filings, holdings, facilities] = await Promise.all([
      pool.query(
        `SELECT COUNT(*)::int AS total, t.t AS "thresholdPts", COUNT(*) FILTER (WHERE s.divergence_pts >= t.t)::int AS "flaggedCount"
           FROM facility_summary s CROSS JOIN unnest($1::numeric[]) AS t(t) GROUP BY t.t ORDER BY t.t`,
        [THRESHOLDS],
      ),
      pool.query(`SELECT COUNT(DISTINCT cik)::int AS bdcs, COUNT(DISTINCT period_end_date)::int AS quarters FROM raw_filings`),
      pool.query(`SELECT COUNT(*)::int AS n FROM normalized_holdings WHERE period_end_date = $1`, [measuredPeriodEnd]),
      pool.query(`SELECT COUNT(*)::int AS n FROM canonical_facilities`),
    ]);
    const body: Record<string, unknown> = {};
    for (const f of LABEL_FIELDS) body[f] = payload && f in payload ? payload[f] : null;
    body.sensitivityTable =
      summary.rows.length > 0 && summary.rows[0].total > 0
        ? summary.rows.map((r) => ({ thresholdPts: Number(r.thresholdPts), flaggedCount: r.flaggedCount }))
        : null;
    body.coverage = {
      bdcs: filings.rows[0].bdcs,
      quarters: filings.rows[0].quarters,
      holdings: holdings.rows[0].n,
      facilities: facilities.rows[0].n,
      measuredPeriodEnd,
    };
    body.evidenceLift = await evidenceLift(pool); // [v2] live, from facility_summary
    body.unexplained = await unexplained(pool); // [v2] FLAGGED facilities with no signal
    body.fieldCoverage = await fieldCoverage(pool); // [v2] live, from facility_comparisons
    body.historyLinks = await historyLinks(pool); // [v2] F3, null until link_history.py has run
    res.json(body);
  });
}
