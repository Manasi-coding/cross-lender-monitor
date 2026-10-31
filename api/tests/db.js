import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { Pool } from "pg";

// A scratch Postgres database built from db/migrations, for tests that need real SQL. Created from DATABASE_URL
// (CI service container or the compose db on localhost) and dropped after.
export const baseUrl = process.env.DATABASE_URL;

function withDb(url, name) {
  const u = new URL(url);
  u.pathname = "/" + name;
  return u.toString();
}

// An error on an idle pooled client must not become an uncaught exception that fails the whole run.
function guard(pool, label) {
  pool.on("error", (err) => {
    console.warn(`[tests/db] idle client error on ${label}: ${err.message}`);
  });
  return pool;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// pool.end() resolves when the pool has asked every client to close, not when the server has seen the sockets go.
// Dropping the database in that gap makes the server terminate the closing backends (57P01). So wait until the
// server itself reports no connection to the scratch database, and never force the drop.
async function waitForNoBackends(admin, name, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    const { rows } = await admin.query(`SELECT COUNT(*)::int AS n FROM pg_stat_activity WHERE datname = $1`, [name]);
    if (rows[0].n === 0) return;
    if (Date.now() > deadline) {
      throw new Error(`${rows[0].n} connection(s) to ${name} are still open after ${timeoutMs} ms, so it was not dropped (no forced drop).`);
    }
    await sleep(25);
  }
}

export async function createScratch(prefix) {
  const name = `${prefix}_${Math.random().toString(16).slice(2, 12)}`;
  const admin = guard(new Pool({ connectionString: withDb(baseUrl , "postgres"), max: 2 }), "the admin pool");
  let pool;
  try {
    await admin.query(`CREATE DATABASE "${name}"`);
    pool = guard(new Pool({ connectionString: withDb(baseUrl , name) }), `the pool of ${name}`);
    const dir = join(__dirname, "..", "..", "db", "migrations");
    for (const f of readdirSync(dir).filter((x) => /^\d{3}_.*\.sql$/.test(x)).sort()) {
      await pool.query(readFileSync(join(dir, f), "utf-8"));
    }
  } catch (e) {
    await pool?.end().catch(() => undefined);
    await admin.end().catch(() => undefined);
    throw e;
  }
  const scratch = pool;
  return {
    pool: scratch,
    // End the pool, wait until the server shows no connection to the database, then drop it without FORCE.
    async drop() {
      try {
        await scratch.end();
        await waitForNoBackends(admin, name);
        await admin.query(`DROP DATABASE IF EXISTS "${name}"`);
      } finally {
        await admin.end();
      }
    },
  };
}
