import { Pool } from "pg";
import { createApp } from "./app";

const pool = new Pool({ connectionString: process.env.DATABASE_URL });
const app = createApp({
  pool,
  enableLabeling: process.env.ENABLE_LABELING === "true",
  nodeEnv: process.env.NODE_ENV ?? "production",
});

const port = Number(process.env.PORT ?? 3000);
app.listen(port, () => {
  console.log(`api listening on ${port}`);
});
