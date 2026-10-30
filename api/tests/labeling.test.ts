import request from "supertest";
import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { Pool } from "pg";
import { createApp } from "../src/app";
import { baseUrl, createScratch } from "./db";

// SPEC tests 15 and 24 for E11 and E12. The flag-off cases need no database. The flag-on cases run against a
// scratch database created from DATABASE_URL (CI service container or the compose db on localhost) and dropped after.

const stub = {
  query: () => {
    throw new Error("the database must not be touched when labeling is off");
  },
} as unknown as Pool;

describe("SPEC 24: flag off", () => {
  it("E11 and E12 are not mounted: 404 in the standard shape", async () => {
    const app = createApp({ pool: stub, enableLabeling: false, nodeEnv: "production", measuredPeriodEnd: "2026-06-30" });
    const a = await request(app).get("/api/label/next");
    const b = await request(app).post("/api/label").send({ sampleId: 1, label: "MATCH", labeledBy: "t" });
    for (const res of [a, b]) {
      expect(res.status).toBe(404);
      expect(res.body.error.code).toBe("NOT_FOUND");
    }
  });
});

const FORBIDDEN = ["score", "status", "band", "scoreband", "phase", "draworder", "draw_order", "score_band"];

function keysDeep(x: unknown, out: string[] = []): string[] {
  if (Array.isArray(x)) x.forEach((v) => keysDeep(v, out));
  else if (x && typeof x === "object") {
    for (const [k, v] of Object.entries(x)) {
      out.push(k);
      keysDeep(v, out);
    }
  }
  return out;
}

describe.skipIf(!baseUrl)("SPEC 24 and 15: flag on", () => {
  let db: Awaited<ReturnType<typeof createScratch>>;
  let pool: Pool;
  let app: ReturnType<typeof createApp>;
  let h: number[]; // holding ids

  async function addHolding(
    filing: number,
    raw: string,
    norm: string,
    cik: string,
    extra: { industry?: string; footnotes?: string; period?: string } = {},
  ) {
    const r = await pool.query(
      `INSERT INTO raw_holdings (filing_id, portfolio_company_raw, source_url) VALUES ($1, $2, 'https://example.test') RETURNING holding_id`,
      [filing, raw],
    );
    const id = r.rows[0].holding_id as number;
    await pool.query(
      `INSERT INTO normalized_holdings (holding_id, bdc_cik, period_end_date, borrower_normalized, industry, instrument_type_norm,
                                        spread_bps, maturity_date, footnotes, source_url)
       VALUES ($1, $2, $6, $3, $4, 'FIRST_LIEN', 475.00, '2030-01-31', $5, 'https://example.test')`,
      [id, cik, norm, extra.industry ?? null, extra.footnotes ?? null, extra.period ?? "2026-06-30"],
    );
    return id;
  }

  async function counts() {
    const out: Record<string, number> = {};
    for (const t of ["raw_filings", "raw_holdings", "normalized_holdings", "candidate_pairs", "label_samples", "labeled_pairs", "band_sizes", "metric_results"]) {
      out[t] = (await pool.query(`SELECT COUNT(*)::int AS n FROM ${t}`)).rows[0].n;
    }
    return out;
  }

  beforeAll(async () => {
    db = await createScratch("test_api");
    pool = db.pool;
    app = createApp({ pool, enableLabeling: true, nodeEnv: "production", measuredPeriodEnd: "2026-06-30" });
  });

  afterAll(async () => {
    await db?.drop();
  });

  beforeEach(async () => {
    await pool.query("TRUNCATE labeled_pairs, label_samples, band_sizes, candidate_pairs, normalized_holdings, raw_holdings, raw_filings RESTART IDENTITY CASCADE");
    const f = [];
    for (const [i, cik] of ["0000000001", "0000000002", "0000000003"].entries()) {
      f.push(
        (
          await pool.query(
            `INSERT INTO raw_filings (cik, bdc_name, form_type, period_end_date, filing_date, accession_number, source_url)
             VALUES ($1, $2, '10-Q', '2026-06-30', '2026-08-10', $3, 'https://example.test') RETURNING filing_id`,
            [cik, `BDC ${i + 1}`, `acc-${i}`],
          )
        ).rows[0].filing_id,
      );
    }
    // 0,1: the pair under test (same borrower "acme"); 2: another filing's spelling of acme; 3: a second holding of acme
    // in the same filing as 0; 4,5: another pair; 6: an unrelated borrower
    h = [
      await addHolding(f[0], "Acme Holdings, LLC", "acme", "0000000001", { industry: "Software", footnotes: "Footnote one" }),
      await addHolding(f[1], "ACME HOLDCO INC", "acme", "0000000002", { industry: "Software" }),
      await addHolding(f[2], "Acme Intermediate, Inc. (dba Acme)", "acme", "0000000003"),
      await addHolding(f[0], "Acme Holdings, LLC", "acme", "0000000001"),
      await addHolding(f[0], "Zed Corp", "zed", "0000000001"),
      await addHolding(f[1], "Zed Corporation", "zed", "0000000002"),
      await addHolding(f[2], "Other Co", "other", "0000000003"),
    ];
    await pool.query(
      `INSERT INTO candidate_pairs (holding_id_a, holding_id_b, score, status) VALUES ($1, $2, 0.97, 'AUTO'), ($3, $4, 0.85, 'REVIEW')`,
      [h[0], h[1], h[4], h[5]],
    );
  });

  async function sample(phase: string, a: number, b: number, order: number, band: string | null = null) {
    return (
      await pool.query(
        `INSERT INTO label_samples (holding_id_a, holding_id_b, phase, score_band, draw_order) VALUES ($1, $2, $3, $4, $5) RETURNING sample_id`,
        [a, b, phase, band, order],
      )
    ).rows[0].sample_id as number;
  }

  it("E11 returns the contract shape, with cross filing names that exclude A and B and are distinct", async () => {
    const sid = await sample("TUNING", h[0], h[1], 1);
    const res = await request(app).get("/api/label/next");
    expect(res.status).toBe(200);
    expect(res.body.sampleId).toBe(sid);
    expect(res.body.progress).toEqual({ labeled: 0, total: 1 });
    expect(Object.keys(res.body).sort()).toEqual(["holdingA", "holdingB", "progress", "sampleId"]);
    const keys = ["holdingId", "rawName", "instrumentType", "maturityDate", "spreadBps", "industry", "footnotes", "crossFilingNames"];
    expect(Object.keys(res.body.holdingA)).toEqual(keys);
    expect(res.body.holdingA).toMatchObject({
      holdingId: h[0], rawName: "Acme Holdings, LLC", instrumentType: "FIRST_LIEN", maturityDate: "2030-01-31",
      spreadBps: "475.00", industry: "Software", footnotes: "Footnote one",
    });
    // holdings 2 and 3 share the normalized name "acme"; 0 and 1 are the pair itself. "Acme Holdings, LLC" is also holding 3's name.
    expect(res.body.holdingA.crossFilingNames).toEqual(["Acme Holdings, LLC", "Acme Intermediate, Inc. (dba Acme)"]);
    expect(res.body.holdingB.crossFilingNames).toEqual(res.body.holdingA.crossFilingNames);
  });

  it("crossFilingNames ignores holdings of another period, even with the same normalized name", async () => {
    const q1Filing = (
      await pool.query(
        `INSERT INTO raw_filings (cik, bdc_name, form_type, period_end_date, filing_date, accession_number, source_url)
         VALUES ('0000000003', 'BDC 3', '10-Q', '2026-03-31', '2026-05-11', 'acc-q1', 'https://example.test') RETURNING filing_id`,
      )
    ).rows[0].filing_id;
    await addHolding(q1Filing, "Acme Prior Quarter Name", "acme", "0000000003", { period: "2026-03-31" });
    await sample("TUNING", h[0], h[1], 1);
    const res = await request(app).get("/api/label/next");
    expect(res.body.holdingA.crossFilingNames).toEqual(["Acme Holdings, LLC", "Acme Intermediate, Inc. (dba Acme)"]);
    expect(JSON.stringify(res.body)).not.toContain("Prior Quarter");
  });

  it("E11 never sends score, status, band, phase or draw order, in any key or value position", async () => {
    await sample("HELDOUT", h[4], h[5], 1, "REVIEW");
    const res = await request(app).get("/api/label/next");
    expect(res.status).toBe(200);
    const keys = keysDeep(res.body).map((k) => k.toLowerCase());
    for (const bad of FORBIDDEN) expect(keys).not.toContain(bad);
    const text = JSON.stringify(res.body);
    expect(text).not.toContain("REVIEW");
    expect(text).not.toContain("HELDOUT");
    expect(text).not.toContain("0.85");
  });

  it("E11 serves TUNING before HELDOUT, then draw order, with progress for the phase being served", async () => {
    const held = await sample("HELDOUT", h[4], h[5], 1, "AUTO");
    const t2 = await sample("TUNING", h[2], h[6], 2);
    const t1 = await sample("TUNING", h[0], h[1], 1);
    let res = await request(app).get("/api/label/next");
    expect(res.body.sampleId).toBe(t1);
    expect(res.body.progress).toEqual({ labeled: 0, total: 2 });
    await request(app).post("/api/label").send({ sampleId: t1, label: "MATCH", labeledBy: "t" });
    res = await request(app).get("/api/label/next");
    expect(res.body.sampleId).toBe(t2);
    expect(res.body.progress).toEqual({ labeled: 1, total: 2 });
    await request(app).post("/api/label").send({ sampleId: t2, label: "UNSURE", labeledBy: "t" });
    res = await request(app).get("/api/label/next");
    expect(res.body.sampleId).toBe(held);
    expect(res.body.progress).toEqual({ labeled: 0, total: 1 });
    await request(app).post("/api/label").send({ sampleId: held, label: "NO_MATCH", labeledBy: "t" });
    res = await request(app).get("/api/label/next");
    expect(res.status).toBe(204);
    expect(res.text).toBe("");
  });

  it("E12 writes labeled_pairs only and derives sampling_method and score_band on the server", async () => {
    const tuning = await sample("TUNING", h[0], h[1], 1);
    const held = await sample("HELDOUT", h[4], h[5], 1, "REVIEW");
    const before = await counts();
    const r1 = await request(app)
      .post("/api/label")
      .send({ sampleId: tuning, label: "MATCH", labeledBy: " me ", samplingMethod: "STRATIFIED", sampling_method: "STRATIFIED", scoreBand: "LOW", holdingIdA: 99 });
    expect(r1.status).toBe(200);
    expect(Object.keys(r1.body)).toEqual(["sampleId", "label", "labeledAt"]);
    expect(r1.body).toMatchObject({ sampleId: tuning, label: "MATCH" });
    expect(Number.isNaN(Date.parse(r1.body.labeledAt))).toBe(false);
    const r2 = await request(app).post("/api/label").send({ sampleId: held, label: "NO_MATCH", labeledBy: "me" });
    expect(r2.status).toBe(200);
    const after = await counts();
    expect(after).toEqual({ ...before, labeled_pairs: before.labeled_pairs + 2 }); // nothing else changed
    const rows = (await pool.query(`SELECT sample_id, holding_id_a, holding_id_b, label, labeled_by, sampling_method, score_band FROM labeled_pairs ORDER BY sample_id`)).rows;
    expect(rows).toEqual([
      { sample_id: tuning, holding_id_a: h[0], holding_id_b: h[1], label: "MATCH", labeled_by: "me", sampling_method: "BLOCKED", score_band: null },
      { sample_id: held, holding_id_a: h[4], holding_id_b: h[5], label: "NO_MATCH", labeled_by: "me", sampling_method: "STRATIFIED", score_band: "REVIEW" },
    ]);
    // candidate_pairs.status is untouched
    expect((await pool.query(`SELECT status FROM candidate_pairs ORDER BY holding_id_a`)).rows.map((r) => r.status)).toEqual(["AUTO", "REVIEW"]);
  });

  it("E12 is an upsert on sampleId: a mis-keyed label is corrected in place", async () => {
    const sid = await sample("TUNING", h[0], h[1], 1);
    await request(app).post("/api/label").send({ sampleId: sid, label: "MATCH", labeledBy: "me" });
    const r = await request(app).post("/api/label").send({ sampleId: sid, label: "UNSURE", labeledBy: "me" });
    expect(r.status).toBe(200);
    const rows = (await pool.query(`SELECT label, sampling_method FROM labeled_pairs`)).rows;
    expect(rows).toEqual([{ label: "UNSURE", sampling_method: "BLOCKED" }]);
  });

  it("E12 returns 400 for an invalid label, a bad sampleId or a missing labeledBy, and 404 for an unknown sampleId", async () => {
    const sid = await sample("TUNING", h[0], h[1], 1);
    const bad = [
      { sampleId: sid, label: "match", labeledBy: "me" },
      { sampleId: sid, label: "MAYBE", labeledBy: "me" },
      { sampleId: sid, labeledBy: "me" },
      { sampleId: "1", label: "MATCH", labeledBy: "me" },
      { sampleId: sid, label: "MATCH", labeledBy: "  " },
      { sampleId: sid, label: "MATCH" },
    ];
    for (const body of bad) {
      const res = await request(app).post("/api/label").send(body);
      expect(res.status, JSON.stringify(body)).toBe(400);
      expect(Object.keys(res.body)).toEqual(["error"]);
    }
    const malformed = await request(app).post("/api/label").set("Content-Type", "application/json").send("{not json");
    expect(malformed.status).toBe(400);
    const unknown = await request(app).post("/api/label").send({ sampleId: 9999, label: "MATCH", labeledBy: "me" });
    expect(unknown.status).toBe(404);
    expect(unknown.body.error.code).toBe("NOT_FOUND");
    expect((await counts()).labeled_pairs).toBe(0);
  });

  it("SPEC 15: a pair confirmed in the review queue is not in labeled_pairs unless independently labeled", async () => {
    const sid = await sample("TUNING", h[4], h[5], 1);
    // what E7 will do when it is built: update candidate_pairs.status only
    await pool.query(`UPDATE candidate_pairs SET status = 'CONFIRMED', updated_at = now() WHERE holding_id_a = $1 AND holding_id_b = $2`, [h[4], h[5]]);
    expect((await counts()).labeled_pairs).toBe(0);
    const next = await request(app).get("/api/label/next");
    expect(next.body.sampleId).toBe(sid); // still waiting for an independent label
    await request(app).post("/api/label").send({ sampleId: sid, label: "NO_MATCH", labeledBy: "me" });
    const rows = (await pool.query(`SELECT label FROM labeled_pairs`)).rows;
    expect(rows).toEqual([{ label: "NO_MATCH" }]); // the label is the labeler's, not the confirmation
    expect((await pool.query(`SELECT status FROM candidate_pairs WHERE holding_id_a = $1`, [h[4]])).rows[0].status).toBe("CONFIRMED");
  });
});
