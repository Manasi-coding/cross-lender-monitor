// Mirrors CONTRACT.md. Only the endpoints the web app calls so far (E11, E12).
// NUMERIC values arrive as strings, as everywhere in this API.

export type LabelValue = "MATCH" | "NO_MATCH" | "UNSURE";

export type LabelHolding = {
  holdingId: number;
  rawName: string | null;
  instrumentType: string;
  maturityDate: string | null;
  spreadBps: string | null;
  industry: string | null;
  footnotes: string | null;
  crossFilingNames: string[];
};

// E11 GET /api/label/next (200 body; 204 has no body; 404 when labeling is off)
export type LabelNext = {
  sampleId: number;
  progress: { labeled: number; total: number };
  holdingA: LabelHolding;
  holdingB: LabelHolding;
};

// E12 POST /api/label
export type LabelRequest = { sampleId: number; label: LabelValue; labeledBy: string };
export type LabelResponse = { sampleId: number; label: LabelValue; labeledAt: string };
