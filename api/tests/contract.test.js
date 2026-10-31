import request from "supertest";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

import { createApp } from "../src/app.js";
import { baseUrl, createScratch } from "./db.js";

// Contract matrix for E1 to E12: the error statuses and codes every endpoint may return, input validation, the standard error shape,
// and the flag-off behaviour of E11 and E12. Success shapes are covered in read.test.js, metrics.test.js and labeling.test.js.
const P2 = "2026-06-30";
const shape = (body) => {
  expect(Object.keys(body)).toEqual(["error"]);
  expect(typeof body.error?.code).toBe("string");
  expect(typeof body.error?.message).toBe("string");
};

describe.skipIf(!baseUrl)("contract matrix E1 to E12", () => {
  let db;
  let pool;
  let off;
  let on;

  beforeAll(async () => {
    db = await createScratch("test_contract");
    pool = db.pool;
    off = createApp({ pool, enableLabeling: false, nodeEnv: "production", measuredPeriodEnd: P2 });
    on = createApp({ pool, enableLabeling: true, nodeEnv: "production", measuredPeriodEnd: P2 });
  });
  afterAll(async () => {
    await db?.drop();
  });

  const BAD_IDS = ["0", "-1", "abc", "1e3", "1.5", "99999999999", "%20", "1%20"];

  it("every id path returns 400 BAD_REQUEST for a bad id, in the standard shape", async () => {
    const paths = ["/api/borrowers/:id/facilities", "/api/facilities/:id/comparison"];
    for (const p of paths) {
      for (const id of BAD_IDS) {
        const res = await request(off).get(p.replace(":id", id));
        expect(res.status, `${p} ${id}`).toBe(400);
        expect(res.body.error.code).toBe("BAD_REQUEST");
        shape(res.body);
      }
    }
    for (const action of ["confirm", "reject"]) {
      for (const id of BAD_IDS) {
        const res = await request(off).post(`/api/review-queue/${id}/2/${action}`);
        expect(res.status, `${action} ${id}`).toBe(400);
        shape(res.body);
      }
    }
  });

  it("an unknown id returns 404 NOT_FOUND for E3, E5, E7 and E8", async () => {
    for (const p of ["/api/borrowers/999/facilities", "/api/facilities/999/comparison"]) {
      const res = await request(off).get(p);
      expect(res.status).toBe(404);
      expect(res.body.error.code).toBe("NOT_FOUND");
      shape(res.body);
    }
    for (const action of ["confirm", "reject"]) {
      const res = await request(off).post(`/api/review-queue/998/999/${action}`);
      expect(res.status).toBe(404);
      shape(res.body);
    }
  });

  it("search is validated on E2 and E4: a repeated or over-long value is 400, a normal or empty one is 200", async () => {
    for (const p of ["/api/borrowers", "/api/facilities"]) {
      for (const q of ["search=a&search=b", `search=${"a".repeat(201)}`]) {
        const res = await request(off).get(`${p}?${q}`);
        expect(res.status, `${p}?${q.slice(0, 30)}`).toBe(400);
        shape(res.body);
      }
      expect((await request(off).get(`${p}?search=`)).status).toBe(200);
      expect((await request(off).get(`${p}?search=${"a".repeat(200)}`)).status).toBe(200);
    }
  });

  it("E4 flag and sort accept only the contract values, and a repeated one is 400", async () => {
    for (const q of ["flag=FLAGGED&flag=MILD", "sort=exposure&sort=borrower", "flag=", "sort="]) {
      const res = await request(off).get(`/api/facilities?${q}`);
      expect(res.status, q).toBe(400);
      shape(res.body);
    }
    for (const q of ["", "flag=AGREEMENT", "flag=MILD&sort=exposure", "sort=borrower"]) expect((await request(off).get(`/api/facilities?${q}`)).status, q).toBe(200);
  });

  it("a wrong method on a known path and an unknown path are 404 NOT_FOUND in the standard shape", async () => {
    for (const [method, path] of [["post", "/api/overview"], ["get", "/api/review-queue/1/2/confirm"], ["put", "/api/borrowers"], ["get", "/api/nope"], ["delete", "/api/metrics"]]) {
      const res = await request(off)[method](path);
      expect(res.status, `${method} ${path}`).toBe(404);
      expect(res.body.error.code).toBe("NOT_FOUND");
      shape(res.body);
    }
  });

  it("E11 and E12 are 404 with the flag off, for any method and body", async () => {
    expect((await request(off).get("/api/label/next")).status).toBe(404);
    for (const body of [{}, { sampleId: 1, label: "MATCH", labeledBy: "x" }]) {
      const res = await request(off).post("/api/label").send(body);
      expect(res.status).toBe(404);
      shape(res.body);
    }
  });

  it("E12 with the flag on returns 400 for malformed JSON and for a body that is not an object, and writes nothing", async () => {
    const bad = await request(on).post("/api/label").set("Content-Type", "application/json").send("{not json");
    expect(bad.status).toBe(400);
    shape(bad.body);
    for (const body of ["[]", "null", '"x"', "1"]) {
      const res = await request(on).post("/api/label").set("Content-Type", "application/json").send(body);
      expect(res.status, body).toBe(400);
      shape(res.body);
    }
    expect((await pool.query(`SELECT COUNT(*)::int AS n FROM labeled_pairs`)).rows[0].n).toBe(0);
  });

  it("E1, E6, E9 and E10 take no input, ignore stray parameters and return 200 on an empty database", async () => {
    for (const p of ["/api/overview", "/api/review-queue", "/api/metrics", "/api/filings"]) {
      const res = await request(off).get(`${p}?x=1&x=2`);
      expect(res.status, p).toBe(200);
    }
  });

  it("every response is JSON with a cache header that allows cheap revalidation (an ETag)", async () => {
    const res = await request(off).get("/api/overview");
    expect(res.headers["content-type"]).toMatch(/application\/json/);
    expect(res.headers.etag).toBeTruthy();
  });
});
