import request from "supertest";
import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import type { Pool } from "pg";
import { createApp } from "../src/app";
import { baseUrl, createScratch } from "./db";

// E9 (SPEC tests 23 and 38). The label-derived payload is written directly, as evaluate.py would write it.
const P2 = "2026-06-30";
const ci = (value: number, n: number) => ({ value, low: value - 0.05, high: Math.min(1, value + 0.05), n });
const PAYLOAD = {
  precisionAutoOnly: { unsureAsNoMatch: ci(0.9, 60), unsureAsMatch: ci(1, 60), unsureExcluded: ci(1, 55) },
  precisionReviewBand: null,
  precisionIfReviewAutoAccepted: null,
  recallAutoOnly: null,
  recallIfReviewAutoAccepted: null,
  blockingRecall: null,
  bands: [{ name: "AUTO", bandSize: 245, sampleSize: 60, labeledInFull: false, counts: { match: 55, noMatch: 0, unsure: 5 }, matchRate: null }],
  unsureCount: 5,
  heldOutCount: 60,
  outOfTime: { periodEnd: "2026-03-31", precisionAutoOnly: null, bands: [], unsureCount: 0, labeledCount: 0 },
  matcherConfigHash: "abc",
};
const LABEL_FIELDS = ["precisionAutoOnly", "precisionReviewBand", "precisionIfReviewAutoAccepted", "recallAutoOnly", "recallIfReviewAutoAccepted", "blockingRecall", "bands", "unsureCount", "heldOutCount", "outOfTime"];

describe.skipIf(!baseUrl)("E9", () => {
  let db: Awaited<ReturnType<typeof createScratch>>;
  let pool: Pool;
  let app: ReturnType<typeof createApp>;

  beforeAll(async () => {
    db = await createScratch("test_metrics");
    pool = db.pool;
    app = createApp({ pool, enableLabeling: false, nodeEnv: "production", measuredPeriodEnd: P2 });
  });
  afterAll(async () => {
    await db?.drop();
  });
  beforeEach(async () => {
    await pool.query(
      `TRUNCATE history_build, history_link_checks, metric_results, facility_summary, facility_comparisons, holding_facility_map, canonical_facilities, canonical_borrowers,
                candidate_pairs, normalized_holdings, raw_holdings, raw_filings RESTART IDENTITY CASCADE`,
    );
  });

  it("test 23: before evaluate.py every label-derived field is null, there is no measured field, and coverage is live", async () => {
    const res = await request(app).get("/api/metrics");
    expect(res.status).toBe(200);
    for (const f of LABEL_FIELDS) expect(res.body[f], f).toBeNull();
    expect("measured" in res.body).toBe(false);
    expect(res.body.sensitivityTable).toBeNull();
    expect(res.body.coverage).toEqual({ bdcs: 0, quarters: 0, holdings: 0, facilities: 0, measuredPeriodEnd: P2 });
  });

  it("serves the newest metric_results row, and flipping candidate_pairs.status changes nothing in the label-derived payload", async () => {
    await pool.query(`INSERT INTO metric_results (matcher_config_hash, payload) VALUES ('old', '{"heldOutCount": 1}'::jsonb)`);
    await pool.query(`INSERT INTO metric_results (matcher_config_hash, payload) VALUES ('abc', $1::jsonb)`, [JSON.stringify(PAYLOAD)]);
    const before = (await request(app).get("/api/metrics")).body;
    expect(before.heldOutCount).toBe(60);
    expect(before.precisionAutoOnly.unsureExcluded.n).toBe(55);
    expect(before.bands[0]).toMatchObject({ name: "AUTO", bandSize: 245, sampleSize: 60 });
    expect(before.outOfTime.periodEnd).toBe("2026-03-31");
    expect("matcherConfigHash" in before).toBe(false);
    await pool.query(`UPDATE candidate_pairs SET status = 'CONFIRMED'`);
    const after = (await request(app).get("/api/metrics")).body;
    for (const f of LABEL_FIELDS) expect(after[f], f).toEqual(before[f]);
  });

  it("sensitivityTable counts facilities with divergencePts at or above 1, 2 and 5, computed live", async () => {
    await pool.query(`INSERT INTO canonical_borrowers (canonical_name, period_end_date) VALUES ('b', $1)`, [P2]);
    for (const [i, d] of ["0.5", "1.0", "2.0", "4.99", "5.0"].entries()) {
      await pool.query(`INSERT INTO canonical_facilities (canonical_borrower_id, period_end_date, instrument_type_norm) VALUES (1, $1, 'FIRST_LIEN')`, [P2]);
      await pool.query(
        `INSERT INTO facility_summary (facility_id, lender_count, excluded_count, divergence_pts, divergence_flag, exposure_usd) VALUES ($1, 2, 0, $2, 'MILD', 0)`,
        [i + 1, d],
      );
    }
    const res = await request(app).get("/api/metrics");
    expect(res.body.sensitivityTable).toEqual([
      { thresholdPts: 1, flaggedCount: 4 },
      { thresholdPts: 2, flaggedCount: 3 },
      { thresholdPts: 5, flaggedCount: 1 },
    ]);
    expect(res.body.coverage.facilities).toBe(5);
  });

  it("historyLinks is null before link_history.py has run, then the linked share, and precision stays null until the hand check exists", async () => {
    expect((await request(app).get("/api/metrics")).body.historyLinks).toBeNull();
    await pool.query(`INSERT INTO history_build (build_id, prior_period_end, period_end_date, current_holdings, linked) VALUES (1, '2026-03-31', $1, 4, 1)`, [P2]);
    let hl = (await request(app).get("/api/metrics")).body.historyLinks;
    expect(hl).toEqual({ priorPeriodEnd: "2026-03-31", linkedShare: null, precision: null });   // no compared holdings: no share to report
  });

  it("test 38: evidenceLift and fieldCoverage appear before evaluate.py, are live, and flipping candidate_pairs.status changes nothing", async () => {
    const empty = (await request(app).get("/api/metrics")).body;
    for (const f of ["evidenceLift", "fieldCoverage", "historyLinks", "unexplained"]) expect(f in empty, f).toBe(true);
    expect(empty.evidenceLift).toBeNull();
    expect(empty.fieldCoverage).toBeNull();
    await pool.query(`INSERT INTO raw_filings (cik, bdc_name, form_type, period_end_date, filing_date, accession_number, source_url) VALUES ('1', 'Alpha', '10-Q', $1, $1, 'a', 'u'), ('2', 'Beta', '10-Q', $1, $1, 'b', 'u')`, [P2]);
    await pool.query(`INSERT INTO canonical_borrowers (canonical_name, period_end_date) VALUES ('b', $1)`, [P2]);
    // 3 FLAGGED facilities (2 with NON_ACCRUAL, 1 with none) and 2 AGREEMENT facilities (none with a signal)
    const rows: [string, string[]][] = [["FLAGGED", ["NON_ACCRUAL"]], ["FLAGGED", ["NON_ACCRUAL", "SPREAD_DIFFERS"]], ["FLAGGED", []], ["AGREEMENT", []], ["AGREEMENT", []]];
    for (const [i, [flag, codes]] of rows.entries()) {
      await pool.query(`INSERT INTO canonical_facilities (canonical_borrower_id, period_end_date, instrument_type_norm) VALUES (1, $1, 'FIRST_LIEN')`, [P2]);
      await pool.query(
        `INSERT INTO facility_summary (facility_id, lender_count, excluded_count, divergence_pts, divergence_flag, exposure_usd, signal_codes) VALUES ($1, 2, 0, 3, $2, 0, $3)`,
        [i + 1, flag, codes],
      );
      for (const [j, cik] of ["1", "2"].entries()) {
        const h = (await pool.query(`INSERT INTO raw_holdings (filing_id, portfolio_company_raw, source_url) VALUES ($1, 'r', 'u') RETURNING holding_id`, [j + 1])).rows[0].holding_id;
        await pool.query(`INSERT INTO normalized_holdings (holding_id, bdc_cik, period_end_date, borrower_normalized, instrument_type_norm, source_url) VALUES ($1, $2, $3, 'b', 'FIRST_LIEN', 'u')`, [h, cik, P2]);
        await pool.query(
          `INSERT INTO facility_comparisons (facility_id, holding_id, period_end_date, bdc_cik, bdc_name, fair_value_pct_par, principal, source_url, floor_bps, pik_bps)
           VALUES ($1, $2, $3, $4, $5, 98, 1000, 'u', $6, 0)`,
          [i + 1, h, P2, cik, j === 0 ? "Alpha" : "Beta", j === 0 ? 50 : null],
        );
      }
    }
    const before = (await request(app).get("/api/metrics")).body;
    const lift = Object.fromEntries(before.evidenceLift.map((r: { code: string }) => [r.code, r]));
    expect(lift.NON_ACCRUAL).toEqual({ code: "NON_ACCRUAL", flaggedShare: 0.666667, flaggedN: 3, agreementShare: 0, agreementN: 2 });
    expect(lift.SPREAD_DIFFERS.flaggedShare).toBe(0.333333);
    expect(before.evidenceLift.map((r: { code: string }) => r.code)).toHaveLength(7);
    expect(before.unexplained).toEqual({ share: 0.333333, withoutSignal: 1, flaggedN: 3 });
    const fc = before.fieldCoverage.filter((r: { field: string }) => r.field === "floorBps");
    expect(fc).toEqual([
      { field: "floorBps", bdcName: "Alpha", parsedShare: 1, n: 5 },
      { field: "floorBps", bdcName: "Beta", parsedShare: 0, n: 5 },
    ]);
    await pool.query(`UPDATE candidate_pairs SET status = 'CONFIRMED'`);
    const after = (await request(app).get("/api/metrics")).body;
    expect(after.evidenceLift).toEqual(before.evidenceLift);
    expect(after.fieldCoverage).toEqual(before.fieldCoverage);
  });
});
