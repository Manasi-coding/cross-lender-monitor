import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { Pool } from "pg";

// A scratch Postgres database built from db/migrations, for tests that need real SQL. Created from DATABASE_URL
// (CI service container or the compose db on localhost) and dropped after.
export const baseUrl = process.env.DATABASE_URL;

function withDb(url: string, name: string): string {
  const u = new URL(url);
  u.pathname = "/" + name;
  return u.toString();
}

export async function createScratch(prefix: string) {
  const name = `${prefix}_${Math.random().toString(16).slice(2, 12)}`;
  const admin = new Pool({ connectionString: withDb(baseUrl!, "postgres") });
  await admin.query(`CREATE DATABASE "${name}"`);
  const pool = new Pool({ connectionString: withDb(baseUrl!, name) });
  const dir = join(__dirname, "..", "..", "db", "migrations");
  for (const f of readdirSync(dir).filter((x) => /^\d{3}_.*\.sql$/.test(x)).sort()) {
    await pool.query(readFileSync(join(dir, f), "utf-8"));
  }
  return {
    pool,
    async drop() {
      await pool.end();
      await admin.query(`DROP DATABASE IF EXISTS "${name}" WITH (FORCE)`);
      await admin.end();
    },
  };
}
