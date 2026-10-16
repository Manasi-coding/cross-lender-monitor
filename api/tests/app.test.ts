import request from "supertest";
import { describe, expect, it } from "vitest";
import type { Pool } from "pg";
import { createApp } from "../src/app";

// The skeleton tests need no database: the pool is a stub that must never be called.
const pool = {
  query: () => {
    throw new Error("the database must not be touched by these tests");
  },
} as unknown as Pool;

describe("error shape", () => {
  it("returns { error: { code, message } } for a route that is not mounted (E11 with the flag off)", async () => {
    const app = createApp({ pool, enableLabeling: false, nodeEnv: "production" });
    const res = await request(app).get("/api/label/next");
    expect(res.status).toBe(404);
    expect(Object.keys(res.body)).toEqual(["error"]);
    expect(typeof res.body.error.code).toBe("string");
    expect(typeof res.body.error.message).toBe("string");
    expect(res.body.error.code).toBe("NOT_FOUND");
  });
});

describe("skeleton routes", () => {
  it("returns 501 NOT_IMPLEMENTED in the standard shape for E5", async () => {
    const app = createApp({ pool, enableLabeling: false, nodeEnv: "production" });
    const res = await request(app).get("/api/facilities/1/comparison");
    expect(res.status).toBe(501);
    expect(res.body).toEqual({
      error: { code: "NOT_IMPLEMENTED", message: "E5 is not implemented yet." },
    });
  });
});
