import { Pool } from "pg";
import { createApp } from "./app.js";

// MEASURED_PERIOD_END is required: E1 returns it, and the UI marks any row from another period as outside the measured set.
const measuredPeriodEnd = process.env.MEASURED_PERIOD_END ?? "";
if (!/^\d{4}-\d{2}-\d{2}$/.test(measuredPeriodEnd)) {
  throw new Error("MEASURED_PERIOD_END must be set to an ISO date (YYYY-MM-DD).");
}

const pool = new Pool({ connectionString: process.env.DATABASE_URL });
const app = createApp({
  pool,
  readOnly: process.env.READ_ONLY === "true",
  enableLabeling: process.env.ENABLE_LABELING === "true",
  nodeEnv: process.env.NODE_ENV ?? "production",
  measuredPeriodEnd,
});

const port = Number(process.env.PORT ?? 3000);
app.listen(port, "0.0.0.0", () => {
  console.log(`api listening on ${port}`);
});
