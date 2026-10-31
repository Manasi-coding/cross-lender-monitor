// The shapes of the API, E1 to E12, as JSDoc typedefs. They document what the web app receives; CONTRACT.md is the source of truth and
// nothing here is checked by a compiler, so the API contract tests are the check. NUMERIC values arrive as strings, as everywhere in this API.
// Use them in other files with, for example, /** @type {import("./types.js").Overview} */.

/** @typedef {"MATCH" | "NO_MATCH" | "UNSURE"} LabelValue */
/** @typedef {"AGREEMENT" | "MILD" | "FLAGGED"} Flag */
/** @typedef {"WIDENED" | "NARROWED" | "CLOSED" | "STABLE" | "NO_PRIOR"} Persistence */
/** @typedef {"NON_ACCRUAL" | "PIK_DIFFERS" | "FLOOR_DIFFERS" | "SPREAD_DIFFERS" | "MATURITY_DIFFERS" | "COST_BASIS_GAP" | "RATE_TYPE_DIFFERS"} SignalCode */

// ---- E11 GET /api/label/next (200 body; 204 has no body; 404 when labeling is off) and E12 POST /api/label
/**
 * @typedef {Object} LabelHolding
 * @property {number} holdingId
 * @property {string | null} rawName
 * @property {string} instrumentType
 * @property {string | null} maturityDate
 * @property {string | null} spreadBps
 * @property {string | null} industry
 * @property {string | null} footnotes
 * @property {string[]} crossFilingNames
 */
/**
 * @typedef {Object} LabelNext
 * @property {number} sampleId
 * @property {{ labeled: number, total: number }} progress
 * @property {LabelHolding} holdingA
 * @property {LabelHolding} holdingB
 */
/** @typedef {{ sampleId: number, label: LabelValue, labeledBy: string }} LabelRequest */
/** @typedef {{ sampleId: number, label: LabelValue, labeledAt: string }} LabelResponse */

// ---- E9 GET /api/metrics. Proportions are in [0, 1]; counts are numbers. Every label-derived field is null until evaluate.py has run.
/** @typedef {{ value: number, low: number, high: number, n: number }} Ci */
/**
 * unsureExcluded is the headline. For precision unsureAsNoMatch is the worst case and unsureAsMatch the best case. For recall the order
 * reverses, so recall is labeled by treatment, not by worst and best.
 * @typedef {{ unsureAsNoMatch: Ci | null, unsureAsMatch: Ci | null, unsureExcluded: Ci | null }} Range
 */
/**
 * @typedef {Object} MetricBand
 * @property {"AUTO" | "REVIEW" | "JUST_BELOW" | "LOW"} name
 * @property {number} bandSize
 * @property {number} sampleSize
 * @property {boolean} labeledInFull
 * @property {{ match: number, noMatch: number, unsure: number }} counts
 * @property {Range | null} matchRate
 */
/** @typedef {{ periodEnd: string, precisionAutoOnly: Range | null, bands: MetricBand[], unsureCount: number, labeledCount: number }} OutOfTime */
/** @typedef {{ code: SignalCode, flaggedShare: number | null, flaggedN: number, agreementShare: number | null, agreementN: number }} EvidenceLiftRow */
/** @typedef {{ field: string, bdcName: string, parsedShare: number | null, n: number }} FieldCoverageRow */
/**
 * @typedef {Object} Metrics
 * @property {Range | null} precisionAutoOnly
 * @property {Range | null} precisionReviewBand
 * @property {Range | null} precisionIfReviewAutoAccepted
 * @property {Range | null} recallAutoOnly
 * @property {Range | null} recallIfReviewAutoAccepted
 * @property {Ci | null} blockingRecall
 * @property {MetricBand[] | null} bands
 * @property {number | null} unsureCount
 * @property {number | null} heldOutCount
 * @property {OutOfTime | null} outOfTime
 * @property {{ thresholdPts: number, flaggedCount: number }[] | null} sensitivityTable
 * @property {{ bdcs: number, quarters: number, holdings: number, facilities: number, measuredPeriodEnd: string }} coverage
 * @property {EvidenceLiftRow[] | null} evidenceLift
 * @property {{ share: number | null, withoutSignal: number, flaggedN: number } | null} unexplained
 * @property {FieldCoverageRow[] | null} fieldCoverage
 * @property {{ priorPeriodEnd: string, linkedShare: number | null, precision: Range | null } | null} historyLinks
 */

// ---- E1 to E8 and E10
/**
 * @typedef {Object} Overview
 * @property {number} bdcCount
 * @property {number} quarterCount
 * @property {string} measuredPeriodEnd
 * @property {number} facilityCount
 * @property {number} pendingReviewCount
 * @property {{ agreement: number, mild: number, flagged: number } | null} divergenceSplit
 * @property {string | null} flaggedExposureUsd
 */
/** @typedef {{ canonicalBorrowerId: number, canonicalName: string, periodEnd: string, lenderCount: number, facilityCount: number }} BorrowerRow */
/**
 * E3: a BorrowerRow plus its facilities.
 * @typedef {BorrowerRow & { facilities: { facilityId: number, instrumentType: string, referenceRate: string | null, maturityBucket: string | null, lenderCount: number }[] }} BorrowerFacilities
 */
/**
 * @typedef {Object} FacilityItem
 * @property {number} facilityId
 * @property {string} borrowerName
 * @property {string} periodEnd
 * @property {string} instrumentType
 * @property {string | null} referenceRate
 * @property {{ min: string | null, max: string | null }} spreadBps
 * @property {string | null} maturityBucket
 * @property {number} lenderCount
 * @property {string} divergencePts
 * @property {Flag} divergenceFlag
 * @property {string} exposureUsd
 * @property {number} signalCount
 * @property {Persistence | null} persistence
 */
/**
 * @typedef {Object} ComparisonRow
 * @property {string} bdcName
 * @property {string | null} spreadBps
 * @property {string} fairValuePctPar
 * @property {string} principal
 * @property {string} sourceUrl
 * @property {string | null} costPctPar
 * @property {string | null} fvPctCost
 * @property {string | null} floorBps
 * @property {string | null} pikBps
 * @property {string | null} maturityDate
 * @property {boolean | null} nonAccrual
 */
/**
 * @typedef {Object} Comparison
 * @property {number} facilityId
 * @property {string} borrowerName
 * @property {string} periodEnd
 * @property {string} instrumentType
 * @property {string | null} referenceRate
 * @property {string | null} maturityBucket
 * @property {ComparisonRow[]} rows
 * @property {number} excludedCount
 * @property {string} divergencePts
 * @property {Flag} divergenceFlag
 * @property {string} exposureUsd
 * @property {SignalCode[]} signals
 * @property {null | { priorPeriodEnd: string, persistence: Persistence, priorDivergencePts: string | null, priorDivergenceFlag: Flag | null, rows: { bdcName: string, priorFairValuePctPar: string | null }[] }} history
 */
/**
 * @typedef {Object} ReviewPair
 * @property {"pair"} type
 * @property {string} periodEnd
 * @property {number} holdingIdA
 * @property {number} holdingIdB
 * @property {string | null} rawNameA
 * @property {string | null} rawNameB
 * @property {string} score
 * @property {string} instrumentType
 * @property {string | null} maturityDateA
 * @property {string | null} maturityDateB
 * @property {string | null} spreadBpsA
 * @property {string | null} spreadBpsB
 * @property {string} sourceUrlA
 * @property {string} sourceUrlB
 */
/**
 * @typedef {Object} ReviewCluster
 * @property {"cluster"} type
 * @property {number} clusterId
 * @property {string} periodEnd
 * @property {"SAME_BDC_COLLISION"} reason
 * @property {{ holdingId: number, bdcName: string, rawName: string | null, instrumentType: string, maturityDate: string | null, spreadBps: string | null, sourceUrl: string }[]} holdings
 * @property {{ holdingIdA: number, holdingIdB: number, score: string, status: string }[]} pairs
 */
/** @typedef {ReviewPair | ReviewCluster} ReviewItem */
/** E7 and E8 response: holdingIdA is always the smaller id. @typedef {{ holdingIdA: number, holdingIdB: number, status: "CONFIRMED" | "REJECTED" }} ReviewDecision */
/** The error body of every endpoint: an HTTP status plus this shape. @typedef {{ error: { code: string, message: string } }} ApiErrorBody */
/** @typedef {{ bdcName: string, cik: string, formType: string, periodEnd: string, holdingsCount: number, sourceUrl: string }} Filing */

export {};
