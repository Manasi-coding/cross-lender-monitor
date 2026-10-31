import request from "supertest";
import { describe, expect, it } from "vitest";

import { createApp } from "../src/app.js";

// The skeleton tests need no database: the pool is a stub that must never be called.
const pool = {
  query: () => {
    throw new Error("the database must not be touched by these tests");
  },
};

describe("error shape", () => {
  it("returns { error: { code, message } } for a route that is not mounted (E11 with the flag off)", async () => {
    const app = createApp({ pool, enableLabeling: false, nodeEnv: "production", measuredPeriodEnd: "2026-06-30" });
    const res = await request(app).get("/api/label/next");
    expect(res.status).toBe(404);
    expect(Object.keys(res.body)).toEqual(["error"]);
    expect(typeof res.body.error.code).toBe("string");
    expect(typeof res.body.error.message).toBe("string");
    expect(res.body.error.code).toBe("NOT_FOUND");
  });
});
