import request from "supertest";
import { describe, expect, it, vi } from "vitest";
import { createApp } from "../src/app.js";

const message = "This is a read-only demo; decisions are disabled";
const writes = [
  "/api/review-queue/1/2/confirm",
  "/api/review-queue/1/2/reject",
  "/api/label",
];

describe("public read-only demo", () => {
  for (const enableLabeling of [false, true]) {
    it.each(writes)(`rejects POST %s before any database access (labeling=${enableLabeling})`, async (path) => {
      const pool = { query: vi.fn(() => { throw new Error("Database must not be touched"); }) };
      const app = createApp({ pool, readOnly: true, enableLabeling, measuredPeriodEnd: "2026-06-30" });
      // Even malformed JSON is rejected by the guard before a body parser runs.
      const res = await request(app).post(path).set("Content-Type", "application/json").send("{");
      expect(res.status).toBe(403);
      expect(res.body).toEqual({ error: { code: "BAD_REQUEST", message } });
      expect(pool.query).not.toHaveBeenCalled();
    });
  }

  it.each(["post", "put", "patch", "delete", "options", "trace"])("rejects %s on API root and unknown routes", async (method) => {
    const pool = { query: vi.fn() };
    const app = createApp({ pool, readOnly: true });
    for (const path of ["/api", "/api/", "/api/unknown", "/API/unknown"]) {
      const res = await request(app)[method](path);
      expect(res.status).toBe(403);
      expect(res.body).toEqual({ error: { code: "BAD_REQUEST", message } });
    }
    expect(pool.query).not.toHaveBeenCalled();
  });

  it.each(["get", "head"])("preserves %s and leaves non-API paths alone", async (method) => {
    const pool = { query: vi.fn().mockResolvedValue({ rows: [] }) };
    const app = createApp({ pool, readOnly: true });
    const res = await request(app)[method]("/api/filings");
    expect(res.status).toBe(200);
    expect(pool.query).toHaveBeenCalledOnce();
    expect((await request(app).post("/outside")).status).toBe(404);
  });

  it.each([undefined, false])("keeps existing writes when readOnly=%s", async (readOnly) => {
    const result = { holdingIdA: 1, holdingIdB: 2, status: "CONFIRMED" };
    const pool = { query: vi.fn().mockResolvedValue({ rows: [result] }) };
    const app = createApp({ pool, readOnly, measuredPeriodEnd: "2026-06-30" });
    const res = await request(app).post(writes[0]);
    expect(res.status).toBe(200);
    expect(res.body).toEqual(result);
    expect(pool.query).toHaveBeenCalledOnce();
  });
});
