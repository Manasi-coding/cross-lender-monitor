import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import request from "supertest";
import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";

import { createApp } from "../src/app.js";
import { baseUrl, createScratch } from "./db.js";

// E1 to E8 and E10 against a scratch database (SPEC tests 12, 13, 22, 28 and 31, plus the contract's shape, sort order,
// 400, 404, 409, DATA_INTEGRITY and null cases). The curated rows are written directly, so the API is tested on its own.
const BDCS = [
  { cik: "0000000001", name: "Alpha BDC" },
  { cik: "0000000002", name: "Beta BDC" },
  { cik: "0000000003", name: "Gamma BDC" },
];
const P2 = "2026-06-30";
const P1 = "2026-03-31";

describe.skipIf(!baseUrl)("E1 to E8 and E10", () => {
  let db;
  let pool;
  let app;
  let filings= [];
  let hSeq = 0;

  beforeAll(async () => {
    db = await createScratch("test_read");
    pool = db.pool;
    app = createApp({ pool, enableLabeling: false, nodeEnv: "production", measuredPeriodEnd: P2 });
  });
  afterAll(async () => {
    await db?.drop();
  });
  beforeEach(async () => {
    await pool.query(
      `TRUNCATE history_build, history_link_checks, facility_history, facility_summary, facility_comparisons, holding_facility_map, canonical_facilities, canonical_borrowers,
                review_cluster_members, review_clusters, candidate_pairs, normalized_holdings, raw_holdings, raw_filings RESTART IDENTITY CASCADE`,
    );
    filings = [];
  });

  async function seedFilings(withQ1 = true) {
    for (const [i, b] of BDCS.entries()) {
      filings.push(
        (
          await pool.query(
            `INSERT INTO raw_filings (cik, bdc_name, form_type, period_end_date, filing_date, accession_number, source_url)
             VALUES ($1, $2, '10-Q', $3, '2026-08-10', $4, $5) RETURNING filing_id`,
            [b.cik, b.name, P2, `acc-${i}`, `https://example.test/filing/${i}`],
          )
        ).rows[0].filing_id,
      );
    }
    if (withQ1) {
      await pool.query(
        `INSERT INTO raw_filings (cik, bdc_name, form_type, period_end_date, filing_date, accession_number, source_url)
         VALUES ($1, $2, '10-Q', $3, '2026-05-11', 'acc-q1', 'https://example.test/q1')`,
        [BDCS[0].cik, BDCS[0].name, P1],
      );
    }
  }

  async function holding(bdc, raw, o= {}) {
    const r = await pool.query(
      `INSERT INTO raw_holdings (filing_id, portfolio_company_raw, source_url) VALUES ($1, $2, $3) RETURNING holding_id`,
      [filings[bdc], raw, `https://example.test/h/${++hSeq}`],
    );
    const id = r.rows[0].holding_id;
    await pool.query(
      `INSERT INTO normalized_holdings (holding_id, bdc_cik, period_end_date, borrower_normalized, instrument_type_norm, spread_bps, maturity_date,
                                        principal, fair_value_pct_par, source_url)
       VALUES ($1, $2, $3, $4, 'FIRST_LIEN', $5, $6, $7, $8, $9)`,
      [id, BDCS[bdc].cik, o.period ?? P2, o.norm ?? raw.toLowerCase(), o.spread ?? null, o.maturity ?? "2030-01-31", o.principal ?? "1000000", o.pct ?? null, `https://example.test/h/${hSeq}`],
    );
    return id;
  }

  async function borrower(name, period = P2) {
    return (await pool.query(`INSERT INTO canonical_borrowers (canonical_name, period_end_date) VALUES ($1, $2) RETURNING canonical_borrower_id`, [name, period])).rows[0].canonical_borrower_id;
  }
  async function facility(
    borrowerId,
    type,
    members,
    s,
  ) {
    const fid = (
      await pool.query(
        `INSERT INTO canonical_facilities (canonical_borrower_id, period_end_date, instrument_type_norm, reference_rate, maturity_bucket)
         VALUES ($1, $2, $3, $4, $5) RETURNING facility_id`,
        [borrowerId, s.period ?? P2, type, s.rate === undefined ? "SOFR" : s.rate, s.maturity === undefined ? "2030-01-31" : s.maturity],
      )
    ).rows[0].facility_id;
    for (const m of members) {
      const hid = await holding(m.bdc, `row ${hSeq + 1}`, { spread: m.spread, pct: m.pct, principal: m.principal });
      await pool.query(
        `INSERT INTO facility_comparisons (facility_id, holding_id, period_end_date, bdc_cik, bdc_name, spread_bps_total, principal, fair_value_pct_par, excluded_reason, source_url)
         VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)`,
        [fid, hid, s.period ?? P2, BDCS[m.bdc].cik, BDCS[m.bdc].name, m.spread, m.principal, m.pct, m.reason ?? null, `https://example.test/src/${hid}`],
      );
    }
    const included = members.filter((m) => m.pct !== null).length;
    await pool.query(
      `INSERT INTO facility_summary (facility_id, lender_count, excluded_count, divergence_pts, divergence_flag, exposure_usd) VALUES ($1, $2, $3, $4, $5, $6)`,
      [fid, Math.max(included, 2), members.length - included, s.div, s.flag, s.exposure],
    );
    return fid;
  }

  const two = (pctA, pctB, spreadA = "500", spreadB = "525")=> [
    { bdc: 0, spread: spreadA, pct: pctA, principal: "5000000" },
    { bdc: 1, spread: spreadB, pct: pctB, principal: "2000000" },
  ];

  // ------------------------------------------------------------------ E1
  it("E1 with an empty database: counts are 0 and the nullable fields are null", async () => {
    const res = await request(app).get("/api/overview");
    expect(res.status).toBe(200);
    expect(res.body).toEqual({
      bdcCount: 0, quarterCount: 0, measuredPeriodEnd: P2, facilityCount: 0, pendingReviewCount: 0, divergenceSplit: null, flaggedExposureUsd: null,
    });
  });

  it("E1 counts BDCs, quarters, facilities, pending review (REVIEW pairs plus clusters) and the divergence split", async () => {
    await seedFilings();
    const b = await borrower("acme");
    await facility(b, "FIRST_LIEN", two("90", "95"), { div: "5", flag: "FLAGGED", exposure: "100000" });
    await facility(b, "REVOLVER", two("90", "92"), { div: "2", flag: "FLAGGED", exposure: "40000.5" });
    await facility(b, "SECOND_LIEN", two("90", "91"), { div: "1", flag: "MILD", exposure: "20000" });
    await facility(b, "UNSECURED", two("90", "90.5"), { div: "0.5", flag: "AGREEMENT", exposure: "10000" });
    const a = await holding(0, "r1"), c = await holding(1, "r2"), d = await holding(0, "r3"), e = await holding(1, "r4");
    await pool.query(`INSERT INTO candidate_pairs (holding_id_a, holding_id_b, score, status) VALUES ($1,$2,0.85,'REVIEW'), ($3,$4,0.9,'AUTO')`, [a, c, d, e]);
    await pool.query(`INSERT INTO review_clusters (period_end_date, reason) VALUES ($1, 'SAME_BDC_COLLISION'), ($1, 'SAME_BDC_COLLISION')`, [P2]);
    const res = await request(app).get("/api/overview");
    expect(Object.keys(res.body)).toEqual(["bdcCount", "quarterCount", "measuredPeriodEnd", "facilityCount", "pendingReviewCount", "divergenceSplit", "flaggedExposureUsd"]);
    expect(res.body).toMatchObject({ bdcCount: 3, quarterCount: 2, measuredPeriodEnd: P2, facilityCount: 4, pendingReviewCount: 3 });
    expect(res.body.divergenceSplit).toEqual({ agreement: 1, mild: 1, flagged: 2 });
    expect(res.body.flaggedExposureUsd).toBe("140000.5"); // [v2] sum over FLAGGED only, Decimal as a string
  });

  // ------------------------------------------------------------------ E2, E3
  it("E2 lists borrowers sorted by name then period descending, counts distinct lending BDCs with a usable mark, and searches safely", async () => {
    await seedFilings();
    const b1 = await borrower("acme"), b2 = await borrower("Beta Corp"), b3 = await borrower("acme", P1);
    await facility(b1, "FIRST_LIEN", [...two("90", "95"), { bdc: 2, spread: null, pct: null, principal: "1", reason: "UNFUNDED_COMMITMENT" }], { div: "5", flag: "FLAGGED", exposure: "1" });
    await facility(b1, "REVOLVER", two("90", "91"), { div: "1", flag: "MILD", exposure: "1" });
    await facility(b2, "FIRST_LIEN", two("90", "90"), { div: "0", flag: "AGREEMENT", exposure: "0" });
    void b3;
    const all = await request(app).get("/api/borrowers");
    expect(all.status).toBe(200);
    expect(all.body.map((r) => [r.canonicalName, r.periodEnd])).toEqual([
      ["Beta Corp", P2], ["acme", P2], ["acme", P1],
    ].sort((x, y) => (x[0] < y[0] ? -1 : x[0] > y[0] ? 1 : x[1] < y[1] ? 1 : -1)));
    const acme = all.body.find((r) => r.canonicalName === "acme" && r.periodEnd === P2);
    expect(Object.keys(acme)).toEqual(["canonicalBorrowerId", "canonicalName", "periodEnd", "lenderCount", "facilityCount"]);
    expect(acme).toMatchObject({ lenderCount: 2, facilityCount: 2 }); // the unfunded third BDC has no usable mark
    expect((await request(app).get("/api/borrowers?search=ACM")).body).toHaveLength(2); // case-insensitive substring: both periods
    expect((await request(app).get("/api/borrowers?search=%25")).body).toEqual([]); // a literal percent sign, not a wildcard
    expect((await request(app).get("/api/borrowers?search=zzz")).body).toEqual([]);
  });

  it("E3 returns the borrower header and facilities sorted by instrument type then maturity bucket; 404 and 400", async () => {
    await seedFilings();
    const b = await borrower("acme");
    const f2 = await facility(b, "REVOLVER", two("90", "91"), { div: "1", flag: "MILD", exposure: "1", maturity: "2031-01-31" });
    const f1 = await facility(b, "FIRST_LIEN", two("90", "95"), { div: "5", flag: "FLAGGED", exposure: "1", maturity: "2032-01-31" });
    const f0 = await facility(b, "FIRST_LIEN", two("90", "91"), { div: "1", flag: "MILD", exposure: "1", maturity: "2029-01-31" });
    const res = await request(app).get(`/api/borrowers/${b}/facilities`);
    expect(res.status).toBe(200);
    expect(Object.keys(res.body)).toEqual(["canonicalBorrowerId", "canonicalName", "periodEnd", "lenderCount", "facilityCount", "facilities"]);
    expect(res.body).toMatchObject({ canonicalBorrowerId: b, canonicalName: "acme", periodEnd: P2, lenderCount: 2, facilityCount: 3 });
    expect(res.body.facilities.map((f) => f.facilityId)).toEqual([f0, f1, f2]);
    expect(Object.keys(res.body.facilities[0])).toEqual(["facilityId", "instrumentType", "referenceRate", "maturityBucket", "lenderCount"]);
    expect((await request(app).get("/api/borrowers/9999/facilities")).status).toBe(404);
    expect((await request(app).get("/api/borrowers/abc/facilities")).status).toBe(400);
  });

  // ------------------------------------------------------------------ E4 (tests 28 and 31)
  async function threeFacilities() {
    await seedFilings();
    const bz = await borrower("zeta"), ba = await borrower("alpha");
    const fz = await facility(bz, "FIRST_LIEN", two("90", "95", "500", "550"), { div: "5", flag: "FLAGGED", exposure: "30000" });
    const fa1 = await facility(ba, "REVOLVER", two("90", "92"), { div: "2", flag: "FLAGGED", exposure: "30000" }); // same exposure as fz, lower divergence
    const fa2 = await facility(ba, "FIRST_LIEN", two("90", "90.5"), { div: "0.5", flag: "AGREEMENT", exposure: "9000" });
    return { fz, fa1, fa2 };
  }

  it("E4 default order is unchanged by the v2 parameters (test 31) and carries the built v2 fields", async () => {
    const { fz, fa1, fa2 } = await threeFacilities();
    const res = await request(app).get("/api/facilities");
    expect(res.status).toBe(200);
    expect(res.body.map((f) => f.facilityId)).toEqual([fa2, fa1, fz]); // borrower, instrumentType ascending
    expect(Object.keys(res.body[0])).toEqual([
      "facilityId", "borrowerName", "periodEnd", "instrumentType", "referenceRate", "spreadBps", "maturityBucket", "lenderCount",
      "divergencePts", "divergenceFlag", "exposureUsd", "signalCount", "persistence",
    ]);
    expect(res.body[2].spreadBps).toEqual({ min: "500", max: "550" });
    expect(res.body[2]).toMatchObject({ divergencePts: "5", divergenceFlag: "FLAGGED", exposureUsd: "30000" });
    expect((await request(app).get("/api/facilities?sort=borrower")).body).toEqual(res.body);
    for (const f of res.body) expect(f.signalCount).toBe(0);
    for (const f of res.body) expect(f.persistence).toBeNull(); // F3 not built: Not yet measured
  });

  it("E4 sort=exposure orders by exposure, then divergence, then facility id, and is stable across calls (test 28)", async () => {
    const { fz, fa1, fa2 } = await threeFacilities();
    const first = await request(app).get("/api/facilities?sort=exposure");
    expect(first.body.map((f) => f.facilityId)).toEqual([fz, fa1, fa2]); // fz and fa1 tie on exposure; fz has the larger divergence
    expect((await request(app).get("/api/facilities?sort=exposure")).body).toEqual(first.body);
    await pool.query(`UPDATE facility_summary SET divergence_pts = 2 WHERE facility_id = $1`, [fz]);
    const tied = await request(app).get("/api/facilities?sort=exposure");
    expect(tied.body.map((f) => f.facilityId)).toEqual([fz, fa1, fa2]); // full tie: ascending facility id (fz was created first)
  });

  it("E4 filters by flag and searches; invalid flag or sort returns 400 (test 31)", async () => {
    const { fz, fa1 } = await threeFacilities();
    const flagged = await request(app).get("/api/facilities?flag=FLAGGED&sort=exposure");
    expect(flagged.body.map((f) => f.facilityId)).toEqual([fz, fa1]);
    expect((await request(app).get("/api/facilities?flag=MILD")).body).toEqual([]);
    expect((await request(app).get("/api/facilities?search=ALP")).body).toHaveLength(2);
    expect((await request(app).get("/api/facilities?search=_")).body).toEqual([]);
    for (const q of ["flag=BAD", "flag=flagged", "sort=points", "sort=exposure&flag=X"]) {
      const res = await request(app).get(`/api/facilities?${q}`);
      expect(res.status, q).toBe(400);
      expect(Object.keys(res.body)).toEqual(["error"]);
    }
  });

  // ------------------------------------------------------------------ E5 (tests 12 and 22)
  it("E5 returns the contract shape with sourceUrl on every row, a fixed periodEnd and no availablePeriods (tests 12 and 22)", async () => {
    await seedFilings();
    const b = await borrower("acme");
    const f = await facility(
      b, "FIRST_LIEN",
      [
        { bdc: 1, spread: "525", pct: "95.5", principal: "2000000" },
        { bdc: 0, spread: "500", pct: "98.5", principal: "5000000" },
        { bdc: 2, spread: null, pct: null, principal: "300000", reason: "UNFUNDED_COMMITMENT" },
      ],
      { div: "3", flag: "FLAGGED", exposure: "60000" },
    );
    const res = await request(app).get(`/api/facilities/${f}/comparison`);
    expect(res.status).toBe(200);
    expect(Object.keys(res.body)).toEqual([
      "facilityId", "borrowerName", "periodEnd", "instrumentType", "referenceRate", "maturityBucket", "rows", "excludedCount", "divergencePts", "divergenceFlag",
      "exposureUsd", "signals", "history",
    ]);
    expect(res.body).not.toHaveProperty("availablePeriods");
    expect(res.body).toMatchObject({ facilityId: f, borrowerName: "acme", periodEnd: P2, excludedCount: 1, divergencePts: "3", divergenceFlag: "FLAGGED" });
    expect(res.body.rows.map((r) => r.bdcName)).toEqual(["Alpha BDC", "Beta BDC"]); // included only, sorted by bdcName
    for (const r of res.body.rows) {
      expect(Object.keys(r)).toEqual([
        "bdcName", "spreadBps", "fairValuePctPar", "principal", "sourceUrl", "costPctPar", "fvPctCost", "floorBps", "pikBps", "maturityDate", "nonAccrual",
      ]);
      expect(r.sourceUrl).toMatch(/^https:\/\/example\.test\/src\//);
    }
    expect(res.body.rows[0]).toMatchObject({ spreadBps: "500", fairValuePctPar: "98.5", principal: "5000000" });
    expect(res.body).toMatchObject({ exposureUsd: "60000", signals: [], history: null });
  });

  it("test 32: E5 carries the dossier, a dossier null stays null (Not disclosed), spreadBps is still total spread and signals use the 7 codes", async () => {
    await seedFilings();
    const b = await borrower("acme");
    const f = await facility(
      b, "FIRST_LIEN",
      [
        { bdc: 0, spread: "525", pct: "98", principal: "5000000" },
        { bdc: 1, spread: "500", pct: "95", principal: "2000000" },
      ],
      { div: "3", flag: "FLAGGED", exposure: "60000" },
    );
    await pool.query(`UPDATE facility_summary SET signal_codes = ARRAY['PIK_DIFFERS','SPREAD_DIFFERS'] WHERE facility_id = $1`, [f]);
    await pool.query(
      `UPDATE facility_comparisons SET cost_pct_par = 99.5, fv_pct_cost = 98.5, floor_bps = 50, pik_bps = 25, maturity_date = '2030-01-31', non_accrual = true
        WHERE facility_id = $1 AND bdc_name = 'Alpha BDC'`,
      [f],
    );
    const res = await request(app).get(`/api/facilities/${f}/comparison`);
    expect(res.body.signals).toEqual(["PIK_DIFFERS", "SPREAD_DIFFERS"]);
    const [alpha, beta] = res.body.rows;
    expect(alpha).toMatchObject({ bdcName: "Alpha BDC", spreadBps: "525", costPctPar: "99.5", fvPctCost: "98.5", floorBps: "50", pikBps: "25", maturityDate: "2030-01-31", nonAccrual: true });
    expect(beta).toMatchObject({ bdcName: "Beta BDC", spreadBps: "500", costPctPar: null, fvPctCost: null, floorBps: null, pikBps: null, maturityDate: null, nonAccrual: null });
    const e4 = (await request(app).get("/api/facilities")).body.find((x) => x.facilityId === f);
    expect(e4.signalCount).toBe(2);
  });

  it("test 36: history is null and persistence is null when F3 is not built, and NO_PRIOR when it is built without two prior marks", async () => {
    await seedFilings();
    const b = await borrower("acme");
    const f = await facility(b, "FIRST_LIEN", two("98", "95"), { div: "3", flag: "FLAGGED", exposure: "60000" });
    expect((await request(app).get(`/api/facilities/${f}/comparison`)).body.history).toBeNull();
    expect((await request(app).get("/api/facilities")).body[0].persistence).toBeNull();
    await pool.query(`INSERT INTO history_build (build_id, prior_period_end, period_end_date, current_holdings, linked) VALUES (1, $1, $2, 10, 0)`, [P1, P2]);
    const built = (await request(app).get(`/api/facilities/${f}/comparison`)).body.history;
    expect(built).toEqual({
      priorPeriodEnd: P1, persistence: "NO_PRIOR", priorDivergencePts: null, priorDivergenceFlag: null,
      rows: [{ bdcName: "Alpha BDC", priorFairValuePctPar: null }, { bdcName: "Beta BDC", priorFairValuePctPar: null }],
    });
    expect((await request(app).get("/api/facilities")).body[0].persistence).toBe("NO_PRIOR");
  });

  it("E5 history carries the stored persistence and each lender's linked prior mark; E4 persistence agrees", async () => {
    await seedFilings();
    const b = await borrower("acme");
    const f = await facility(b, "FIRST_LIEN", two("98", "95"), { div: "3", flag: "FLAGGED", exposure: "60000" });
    const cur = (await pool.query(`SELECT holding_id, bdc_cik FROM facility_comparisons WHERE facility_id = $1 ORDER BY bdc_name`, [f])).rows;
    const prior = [];
    for (const [i, c] of cur.entries()) {
      const fi = (await pool.query(`SELECT filing_id FROM raw_filings WHERE cik = $1 AND period_end_date = $2`, [c.bdc_cik, i === 0 ? P1 : P1])).rows[0]?.filing_id
        ?? (await pool.query(`INSERT INTO raw_filings (cik, bdc_name, form_type, period_end_date, filing_date, accession_number, source_url) VALUES ($1, 'x', '10-Q', $2, '2026-05-11', $3, 'u') RETURNING filing_id`, [c.bdc_cik, P1, `acc-prior-${i}`])).rows[0].filing_id;
      const h = (await pool.query(`INSERT INTO raw_holdings (filing_id, portfolio_company_raw, source_url) VALUES ($1, 'p', 'u') RETURNING holding_id`, [fi])).rows[0].holding_id;
      await pool.query(`INSERT INTO normalized_holdings (holding_id, bdc_cik, period_end_date, borrower_normalized, instrument_type_norm, fair_value_pct_par, source_url) VALUES ($1, $2, $3, 'p', 'FIRST_LIEN', $4, 'u')`, [h, c.bdc_cik, P1, i === 0 ? "97.5" : "97"]);
      await pool.query(`INSERT INTO holding_history_links (holding_id, prior_holding_id, link_rule) VALUES ($1, $2, 'EXACT_KEY')`, [c.holding_id, h]);
      prior.push(h);
    }
    await pool.query(`INSERT INTO history_build (build_id, prior_period_end, period_end_date, current_holdings, linked) VALUES (1, $1, $2, 2, 2)`, [P1, P2]);
    await pool.query(`INSERT INTO facility_history (facility_id, prior_period_end, prior_lender_count, prior_divergence_pts, prior_divergence_flag, persistence) VALUES ($1, $2, 2, 0.5, 'AGREEMENT', 'WIDENED')`, [f, P1]);
    const hist = (await request(app).get(`/api/facilities/${f}/comparison`)).body.history;
    expect(hist).toEqual({
      priorPeriodEnd: P1, persistence: "WIDENED", priorDivergencePts: "0.5", priorDivergenceFlag: "AGREEMENT",
      rows: [{ bdcName: "Alpha BDC", priorFairValuePctPar: "97.5" }, { bdcName: "Beta BDC", priorFairValuePctPar: "97" }],
    });
    expect((await request(app).get("/api/facilities")).body[0].persistence).toBe("WIDENED");
  });

  it("E5 returns 500 DATA_INTEGRITY when a facility has fewer than 2 included rows (test 22), 404 for an unknown id and 400 for a bad id", async () => {
    await seedFilings();
    const b = await borrower("acme");
    const f = await facility(b, "FIRST_LIEN", [{ bdc: 0, spread: "500", pct: "98", principal: "5000000" }, { bdc: 1, spread: null, pct: null, principal: "1", reason: "ZERO_OR_NULL_PRINCIPAL" }], {
      div: "0", flag: "AGREEMENT", exposure: "0",
    });
    const res = await request(app).get(`/api/facilities/${f}/comparison`);
    expect(res.status).toBe(500);
    expect(res.body.error.code).toBe("DATA_INTEGRITY");
    expect((await request(app).get("/api/facilities/99999/comparison")).status).toBe(404);
    expect((await request(app).get("/api/facilities/x/comparison")).status).toBe(400);
  });

  // ------------------------------------------------------------------ E6
  async function pair(a, b, score, status) {
    const [x, y] = a < b ? [a, b] : [b, a];
    await pool.query(`INSERT INTO candidate_pairs (holding_id_a, holding_id_b, score, status) VALUES ($1, $2, $3, $4)`, [x, y, score, status]);
  }

  it("E6 lists clusters first, then REVIEW pairs by score descending then ids; a cluster carries its members and its AUTO or CONFIRMED edges", async () => {
    await seedFilings();
    const p1 = await holding(0, "Pair One A", { spread: "500" }), p2 = await holding(1, "Pair One B", { spread: "510" });
    const q1 = await holding(0, "Pair Two A"), q2 = await holding(1, "Pair Two B");
    const n1 = await holding(0, "No Match A"), n2 = await holding(1, "No Match B");
    await pair(p1, p2, "0.85", "REVIEW");
    await pair(q1, q2, "0.9167", "REVIEW");
    await pair(n1, n2, "0.5", "NO_MATCH");
    const c1 = await holding(0, "Cluster A1"), c2 = await holding(0, "Cluster A2"), c3 = await holding(1, "Cluster B1");
    await pair(c1, c3, "0.97", "AUTO");
    await pair(c2, c3, "0.95", "CONFIRMED");
    await pair(c1, c2, "0.81", "REVIEW"); // inside the cluster but not an edge that formed it, and it is a REVIEW pair
    const cl = (await pool.query(`INSERT INTO review_clusters (period_end_date, reason) VALUES ($1, 'SAME_BDC_COLLISION') RETURNING cluster_id`, [P2])).rows[0].cluster_id;
    for (const h of [c1, c2, c3]) await pool.query(`INSERT INTO review_cluster_members (cluster_id, holding_id) VALUES ($1, $2)`, [cl, h]);

    const res = await request(app).get("/api/review-queue");
    expect(res.status).toBe(200);
    expect(res.body.map((i) => i.type)).toEqual(["cluster", "pair", "pair", "pair"]);
    const cluster = res.body[0];
    expect(Object.keys(cluster)).toEqual(["type", "clusterId", "periodEnd", "reason", "holdings", "pairs"]);
    expect(cluster).toMatchObject({ clusterId: cl, periodEnd: P2, reason: "SAME_BDC_COLLISION" });
    expect(cluster.holdings.map((h) => h.holdingId)).toEqual([c1, c2, c3]);
    expect(Object.keys(cluster.holdings[0])).toEqual(["holdingId", "bdcName", "rawName", "instrumentType", "maturityDate", "spreadBps", "sourceUrl"]);
    expect(cluster.pairs.map((p) => [p.holdingIdA, p.holdingIdB, p.status])).toEqual([
      [c1, c3, "AUTO"], [c2, c3, "CONFIRMED"],
    ]);
    const pairs = res.body.slice(1);
    expect(Object.keys(pairs[0])).toEqual([
      "type", "periodEnd", "holdingIdA", "holdingIdB", "rawNameA", "rawNameB", "score", "instrumentType", "maturityDateA", "maturityDateB",
      "spreadBpsA", "spreadBpsB", "sourceUrlA", "sourceUrlB",
    ]);
    expect(pairs.map((p) => Number(p.score))).toEqual([0.9167, 0.85, 0.81]); // NO_MATCH and AUTO pairs are not listed
    expect(pairs[1]).toMatchObject({ rawNameA: "Pair One A", rawNameB: "Pair One B", spreadBpsA: "500", spreadBpsB: "510", maturityDateA: "2030-01-31" });
  });

  it("pairs and clusters of another period are neither listed by E6 nor counted by E1 pendingReviewCount (measured period only)", async () => {
    await seedFilings();
    const mk = async (period, tag) => ({
      a: await holding(0, `${tag} A`, { period }), b: await holding(1, `${tag} B`, { period }),
      c: await holding(0, `${tag} C`, { period }), d: await holding(0, `${tag} D`, { period }), e: await holding(1, `${tag} E`, { period }),
    });
    const m = await mk(P2, "Measured"), o = await mk(P1, "Prior");
    for (const [x, period] of [[m, P2], [o, P1]]) {
      await pair(x.a, x.b, period === P2 ? "0.85" : "0.9", "REVIEW");
      const cl = (await pool.query(`INSERT INTO review_clusters (period_end_date, reason) VALUES ($1, 'SAME_BDC_COLLISION') RETURNING cluster_id`, [period])).rows[0].cluster_id;
      for (const h of [x.c, x.d, x.e]) await pool.query(`INSERT INTO review_cluster_members (cluster_id, holding_id) VALUES ($1, $2)`, [cl, h]);
      await pair(x.c, x.e, "0.97", "AUTO");
      await pair(x.d, x.e, "0.96", "AUTO");
    }
    // a pair that spans two periods cannot be a candidate, but it must not be listed even if one were stored
    await pair(m.c, o.e, "0.88", "REVIEW");
    const queue = await request(app).get("/api/review-queue");
    expect(queue.body.map((i) => i.type)).toEqual(["cluster", "pair"]);
    expect(queue.body.every((i) => i.periodEnd === P2)).toBe(true);
    expect(queue.body[0].holdings.map((h) => h.holdingId)).toEqual([m.c, m.d, m.e]);
    expect(queue.body[0].pairs).toHaveLength(2);
    expect(queue.body[1]).toMatchObject({ holdingIdA: m.a, holdingIdB: m.b });
    const overview = await request(app).get("/api/overview");
    expect(overview.body.pendingReviewCount).toBe(2); // 1 measured REVIEW pair + 1 measured cluster, not the 2 prior-period items or the mixed pair
    // the filter follows MEASURED_PERIOD_END: the same data seen from the other quarter
    const other = createApp({ pool, enableLabeling: false, nodeEnv: "production", measuredPeriodEnd: P1 });
    const q1 = await request(other).get("/api/review-queue");
    expect(q1.body.map((i) => [i.type, i.periodEnd])).toEqual([["cluster", P1], ["pair", P1]]);
    expect((await request(other).get("/api/overview")).body.pendingReviewCount).toBe(2);
  });

  it("E6 is an empty list when nothing is waiting", async () => {
    expect((await request(app).get("/api/review-queue")).body).toEqual([]);
  });

  // ------------------------------------------------------------------ E7 and E8 (test 13)
  async function statusOf(a, b) {
    return (await pool.query(`SELECT status FROM candidate_pairs WHERE holding_id_a = $1 AND holding_id_b = $2`, [a, b])).rows[0].status;
  }
  async function fresh(status) {
    if (filings.length === 0) await seedFilings(false);
    const a = await holding(0, "A" + ++hSeq), b = await holding(1, "B" + hSeq);
    const [x, y] = a < b ? [a, b] : [b, a];
    await pair(x, y, "0.85", status);
    return [x, y];
  }

  it("E7 confirms a REVIEW pair in either id order and returns 409 from any other status (test 13)", async () => {
    const [a, b] = await fresh("REVIEW");
    const ok = await request(app).post(`/api/review-queue/${b}/${a}/confirm`); // reversed ids
    expect(ok.status).toBe(200);
    expect(ok.body).toEqual({ holdingIdA: a, holdingIdB: b, status: "CONFIRMED" });
    expect(await statusOf(a, b)).toBe("CONFIRMED");
    for (const s of ["AUTO", "NO_MATCH", "CONFIRMED", "REJECTED"]) {
      await pool.query(`UPDATE candidate_pairs SET status = $3 WHERE holding_id_a = $1 AND holding_id_b = $2`, [a, b, s]);
      const res = await request(app).post(`/api/review-queue/${a}/${b}/confirm`);
      expect(res.status, s).toBe(409);
      expect(res.body.error.code).toBe("CONFLICT");
      expect(await statusOf(a, b)).toBe(s); // untouched
    }
  });

  it("E8 rejects AUTO, REVIEW and CONFIRMED pairs in either id order and returns 409 for NO_MATCH and REJECTED (test 13)", async () => {
    const [a, b] = await fresh("AUTO");
    for (const [i, from] of ["AUTO", "REVIEW", "CONFIRMED"].entries()) {
      await pool.query(`UPDATE candidate_pairs SET status = $3 WHERE holding_id_a = $1 AND holding_id_b = $2`, [a, b, from]);
      const res = await request(app).post(i % 2 ? `/api/review-queue/${a}/${b}/reject` : `/api/review-queue/${b}/${a}/reject`);
      expect(res.status, from).toBe(200);
      expect(res.body).toEqual({ holdingIdA: a, holdingIdB: b, status: "REJECTED" });
      expect(await statusOf(a, b)).toBe("REJECTED");
    }
    for (const s of ["NO_MATCH", "REJECTED"]) {
      await pool.query(`UPDATE candidate_pairs SET status = $3 WHERE holding_id_a = $1 AND holding_id_b = $2`, [a, b, s]);
      expect((await request(app).post(`/api/review-queue/${a}/${b}/reject`)).status, s).toBe(409);
    }
  });

  it("E7 and E8 return 404 for a pair outside the measured period and leave its status alone", async () => {
    await seedFilings();
    const a = await holding(0, "Old A", { period: P1 });
    const b = await holding(1, "Old B", { period: P1 });
    const [x, y] = a < b ? [a, b] : [b, a];
    await pair(x, y, "0.85", "REVIEW");
    for (const action of ["confirm", "reject"]) {
      const res = await request(app).post(`/api/review-queue/${x}/${y}/${action}`);
      expect(res.status, action).toBe(404);
      expect(res.body.error.code).toBe("NOT_FOUND");
    }
    expect(await statusOf(x, y)).toBe("REVIEW");
    // the same pair is reachable when its quarter is the measured one
    const other = createApp({ pool, enableLabeling: false, nodeEnv: "production", measuredPeriodEnd: P1 });
    expect((await request(other).post(`/api/review-queue/${x}/${y}/confirm`)).status).toBe(200);
  });

  it("E7 and E8 return 404 for an unknown pair and 400 for a bad id", async () => {
    await fresh("REVIEW");
    expect((await request(app).post("/api/review-queue/90001/90002/confirm")).status).toBe(404);
    expect((await request(app).post("/api/review-queue/90001/90002/reject")).status).toBe(404);
    expect((await request(app).post("/api/review-queue/1/1/reject")).status).toBe(404);
    expect((await request(app).post("/api/review-queue/a/2/confirm")).status).toBe(400);
  });

  it("E7 and E8 write candidate_pairs.status and updated_at only: curated tables, labeled_pairs and the scores do not change", async () => {
    await seedFilings();
    const b = await borrower("acme");
    await facility(b, "FIRST_LIEN", two("90", "95"), { div: "5", flag: "FLAGGED", exposure: "1" });
    const [x, y] = await fresh("REVIEW");
    const snap = async () =>
      JSON.stringify([
        (await pool.query(`SELECT * FROM facility_summary ORDER BY 1`)).rows,
        (await pool.query(`SELECT * FROM facility_comparisons ORDER BY 1, 2`)).rows,
        (await pool.query(`SELECT * FROM canonical_facilities ORDER BY 1`)).rows,
        (await pool.query(`SELECT * FROM labeled_pairs`)).rows,
        (await pool.query(`SELECT holding_id_a, holding_id_b, score FROM candidate_pairs ORDER BY 1, 2`)).rows,
      ]);
    const before = await snap();
    const t0 = (await pool.query(`SELECT updated_at FROM candidate_pairs WHERE holding_id_a = $1`, [x])).rows[0].updated_at;
    await request(app).post(`/api/review-queue/${x}/${y}/confirm`);
    await request(app).post(`/api/review-queue/${x}/${y}/reject`);
    expect(await snap()).toBe(before);
    expect(((await pool.query(`SELECT updated_at FROM candidate_pairs WHERE holding_id_a = $1`, [x])).rows[0].updated_at).getTime()).toBeGreaterThanOrEqual(t0.getTime());
  });

  // ------------------------------------------------------------------ E10 and the standing rules
  it("E10 lists filings, periodEnd descending then bdcName ascending, with the holdings count", async () => {
    await seedFilings();
    await holding(0, "one");
    await holding(0, "two");
    const res = await request(app).get("/api/filings");
    expect(res.status).toBe(200);
    expect(res.body.map((f) => [f.bdcName, f.periodEnd])).toEqual([
      ["Alpha BDC", P2], ["Beta BDC", P2], ["Gamma BDC", P2], ["Alpha BDC", P1],
    ]);
    expect(Object.keys(res.body[0])).toEqual(["bdcName", "cik", "formType", "periodEnd", "holdingsCount", "sourceUrl"]);
    expect(res.body[0].holdingsCount).toBe(2);
  });

  it("E11 and E12 are 404 with the flag off", async () => {
    expect((await request(app).get("/api/label/next")).status).toBe(404);
    expect((await request(app).post("/api/label").send({})).status).toBe(404);
  });

  it("the API source never reads config.yaml", () => {
    const dir = join(__dirname, "..", "src");
    for (const f of readdirSync(dir).filter((x) => x.endsWith(".js"))) {
      const text = readFileSync(join(dir, f), "utf-8");
      expect(/config\.yaml|from "yaml"|require\("yaml"\)/.test(text), f).toBe(false);
    }
  });
});
