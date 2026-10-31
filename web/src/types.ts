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

// E9 GET /api/metrics. Proportions are in [0, 1]; counts are numbers. Every label-derived field is null until evaluate.py has run.
export type Ci = { value: number; low: number; high: number; n: number };
// [v2] unsureExcluded is the headline; unsureAsNoMatch is the worst case and unsureAsMatch the best case.
export type Range = { unsureAsNoMatch: Ci | null; unsureAsMatch: Ci | null; unsureExcluded: Ci | null };
export type MetricBand = {
  name: "AUTO" | "REVIEW" | "JUST_BELOW" | "LOW";
  bandSize: number;
  sampleSize: number;
  labeledInFull: boolean;
  counts: { match: number; noMatch: number; unsure: number };
  matchRate: Range | null;
};
export type OutOfTime = { periodEnd: string; precisionAutoOnly: Range | null; bands: MetricBand[]; unsureCount: number; labeledCount: number };
export type EvidenceLiftRow = { code: string; flaggedShare: number | null; flaggedN: number; agreementShare: number | null; agreementN: number };
export type FieldCoverageRow = { field: string; bdcName: string; parsedShare: number | null; n: number };
export type Metrics = {
  precisionAutoOnly: Range | null;
  precisionReviewBand: Range | null;
  precisionIfReviewAutoAccepted: Range | null;
  recallAutoOnly: Range | null;
  recallIfReviewAutoAccepted: Range | null;
  blockingRecall: Ci | null;
  bands: MetricBand[] | null;
  unsureCount: number | null;
  heldOutCount: number | null;
  outOfTime: OutOfTime | null;
  sensitivityTable: { thresholdPts: number; flaggedCount: number }[] | null;
  coverage: { bdcs: number; quarters: number; holdings: number; facilities: number; measuredPeriodEnd: string };
  evidenceLift: EvidenceLiftRow[] | null;
  unexplained: { share: number | null; withoutSignal: number; flaggedN: number } | null;
  fieldCoverage: FieldCoverageRow[] | null;
  historyLinks: { priorPeriodEnd: string; linkedShare: number; precision: Range | null } | null;
};

// E1 to E8 and E10 (CONTRACT.md). NUMERIC values arrive as strings.
export type Flag = "AGREEMENT" | "MILD" | "FLAGGED";
export type Persistence = "WIDENED" | "NARROWED" | "CLOSED" | "STABLE" | "NO_PRIOR";
export type SignalCode = "NON_ACCRUAL" | "PIK_DIFFERS" | "FLOOR_DIFFERS" | "SPREAD_DIFFERS" | "MATURITY_DIFFERS" | "COST_BASIS_GAP" | "RATE_TYPE_DIFFERS";

export type Overview = {
  bdcCount: number;
  quarterCount: number;
  measuredPeriodEnd: string;
  facilityCount: number;
  pendingReviewCount: number;
  divergenceSplit: { agreement: number; mild: number; flagged: number } | null;
  flaggedExposureUsd: string | null;
};
export type BorrowerRow = { canonicalBorrowerId: number; canonicalName: string; periodEnd: string; lenderCount: number; facilityCount: number };
export type BorrowerFacilities = BorrowerRow & {
  facilities: { facilityId: number; instrumentType: string; referenceRate: string | null; maturityBucket: string | null; lenderCount: number }[];
};
export type FacilityItem = {
  facilityId: number;
  borrowerName: string;
  periodEnd: string;
  instrumentType: string;
  referenceRate: string | null;
  spreadBps: { min: string | null; max: string | null };
  maturityBucket: string | null;
  lenderCount: number;
  divergencePts: string;
  divergenceFlag: Flag;
  exposureUsd: string;
  signalCount: number;
  persistence: Persistence | null;
};
export type ComparisonRow = {
  bdcName: string;
  spreadBps: string | null;
  fairValuePctPar: string;
  principal: string;
  sourceUrl: string;
  costPctPar: string | null;
  fvPctCost: string | null;
  floorBps: string | null;
  pikBps: string | null;
  maturityDate: string | null;
  nonAccrual: boolean | null;
};
export type Comparison = {
  facilityId: number;
  borrowerName: string;
  periodEnd: string;
  instrumentType: string;
  referenceRate: string | null;
  maturityBucket: string | null;
  rows: ComparisonRow[];
  excludedCount: number;
  divergencePts: string;
  divergenceFlag: Flag;
  exposureUsd: string;
  signals: SignalCode[];
  history: null | {
    priorPeriodEnd: string;
    persistence: Persistence;
    priorDivergencePts: string | null;
    priorDivergenceFlag: Flag | null;
    rows: { bdcName: string; priorFairValuePctPar: string | null }[];
  };
};
export type ReviewPair = {
  type: "pair";
  periodEnd: string;
  holdingIdA: number;
  holdingIdB: number;
  rawNameA: string | null;
  rawNameB: string | null;
  score: string;
  instrumentType: string;
  maturityDateA: string | null;
  maturityDateB: string | null;
  spreadBpsA: string | null;
  spreadBpsB: string | null;
  sourceUrlA: string;
  sourceUrlB: string;
};
export type ReviewCluster = {
  type: "cluster";
  clusterId: number;
  periodEnd: string;
  reason: string;
  holdings: { holdingId: number; bdcName: string; rawName: string | null; instrumentType: string; maturityDate: string | null; spreadBps: string | null; sourceUrl: string }[];
  pairs: { holdingIdA: number; holdingIdB: number; score: string; status: string }[];
};
export type ReviewItem = ReviewPair | ReviewCluster;
export type Filing = { bdcName: string; cik: string; formType: string; periodEnd: string; holdingsCount: number; sourceUrl: string };
