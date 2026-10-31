import type { Response } from "express";

// Error shape from CONTRACT.md: an HTTP status plus { error: { code, message } }.
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

export function sendError(res: Response, status: number, code: string, message: string) {
  res.status(status).json({ error: { code, message } });
}

// A path id: a positive integer that fits the INT columns. Anything else is bad input (400), not a missing row.
export function parseId(raw: string, what = "id"): number {
  if (!/^\d{1,9}$/.test(raw) || Number(raw) < 1) {
    throw new ApiError(400, "BAD_REQUEST", `${what} must be a positive integer.`);
  }
  return Number(raw);
}

// search parameters are case-insensitive substring matches with the LIKE wildcards escaped (CONTRACT.md).
// A repeated or structured parameter (?search=a&search=b, ?search[x]=1) and an over-long one are bad input (400), not an empty search.
export function likePattern(search: unknown): string | null {
  if (search !== undefined && typeof search !== "string") throw new ApiError(400, "BAD_REQUEST", "search must be a single text value.");
  if (typeof search === "string" && search.length > 200) throw new ApiError(400, "BAD_REQUEST", "search must be at most 200 characters.");
  if (typeof search !== "string" || search.trim() === "") return null;
  return "%" + search.trim().replace(/[\\%_]/g, (c) => "\\" + c) + "%";
}
