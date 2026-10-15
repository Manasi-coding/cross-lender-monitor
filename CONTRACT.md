CONTRACT.md: API contract, E1 to E12
Single source of truth for endpoint shapes, conventions, errors and write rules. SPEC.md owns scope, schema, evaluation method, tests and schedule. This file owns the API. phase_wise.md and frontend.md carry only the endpoint index (ID, method, path, page), copied from the Endpoint list below so both plans name the same endpoints, and they link here for everything else. If an endpoint changes, change this file first, then the index in both plans.
Reflects decisions A1 (one measured quarter, no period selector), A2 (exact-name borrower grouping), A8 (no review-confirmed metric) and the accepted fixes from the discrepancy review.
Conventions
Base path /api. JSON, camelCase, dates as YYYY-MM-DD.
fairValuePctPar and divergencePts are in points of par (98.5 means 98.5% of par, 3.2 means 3.2 points). Metric values and interval bounds are proportions in [0, 1].
Null rule. A field that has not been computed yet is null. The UI renders null as "Not yet measured". There is no measured flag anywhere.
Errors use an HTTP status plus { "error": { "code": string, "message": string } }. 400 bad input, 404 unknown id or route not mounted, 409 invalid status transition, 500 with code DATA_INTEGRITY when stored data breaks an invariant.
Lists are unpaginated by design (3 BDCs, small result sets). Sort orders are fixed so responses are deterministic.
All SQL is parameterized. search params are case-insensitive substring matches with wildcards escaped.
Borrower, facility and cluster IDs are regenerated on every compare.py run. They are stable across page loads, not across a rebuild.
Every spread is total spread in basis points: cash spread plus PIK.
Writes: E7 and E8 update candidate_pairs.status and updated_at only. E12 writes labeled_pairs only and is mounted only when ENABLE_LABELING=true (default false, no auth). Every other endpoint is read-only.
Shared types
Ci    = { value, low, high, n }
Range = { unsureAsNoMatch: Ci, unsureAsMatch: Ci }

low and high are a 95% interval (Wilson or bootstrap, stated per field in E9). n is the sample size behind the interval. For recall, the UNSURE-as-MATCH value is the lower one, so the UI shows ranges as low to high, not in field order.
Endpoint list
ID
Method and path
Page
E1
GET /api/overview
Overview
E2
GET /api/borrowers?search=
Borrowers
E3
GET /api/borrowers/:id/facilities
Borrower Detail
E4
GET /api/facilities?search=
Facilities
E5
GET /api/facilities/:id/comparison
Facility Comparison
E6
GET /api/review-queue
Review Queue
E7
POST /api/review-queue/:idA/:idB/confirm
Review Queue
E8
POST /api/review-queue/:idA/:idB/reject
Review Queue
E9
GET /api/metrics
Metrics
E10
GET /api/filings
Filings
E11
GET /api/label/next (flag-gated)
Labeling
E12
POST /api/label (flag-gated)
Labeling

Shapes
E1 GET /api/overview
{ bdcCount, quarterCount, measuredPeriodEnd, facilityCount, pendingReviewCount,
  divergenceSplit: { agreement, mild, flagged } | null }

All counts are integers. divergenceSplit holds facility counts, not percentages (the UI computes percentages). It is null until facility_summary has rows.
pendingReviewCount is REVIEW pairs plus review clusters.
measuredPeriodEnd lets the UI mark any row from another period as outside the measured set.
E2 GET /api/borrowers?search=
[ { canonicalBorrowerId, canonicalName, periodEnd, lenderCount, facilityCount } ]

A borrower exists in exactly one period. Sort: canonicalName ascending, periodEnd descending.
lenderCount is the number of distinct BDCs with an included holding across the borrower's facilities.
E3 GET /api/borrowers/:id/facilities
{ canonicalBorrowerId, canonicalName, periodEnd, lenderCount, facilityCount,
  facilities: [ { facilityId, instrumentType, referenceRate, maturityBucket, lenderCount } ] }

Carries the borrower header so a direct link or refresh works without the E2 list. Sort facilities by instrumentType, then maturityBucket, ascending. 404 for an unknown id.
E4 GET /api/facilities?search=
[ { facilityId, borrowerName, periodEnd, instrumentType, referenceRate,
    spreadBps: { min, max }, maturityBucket, lenderCount } ]

search matches borrowerName. spreadBps is the min and max total spread over included holdings. Sort: borrowerName, instrumentType ascending, then periodEnd descending.
E5 GET /api/facilities/:id/comparison
{ facilityId, borrowerName, periodEnd, instrumentType, referenceRate, maturityBucket,
  rows: [ { bdcName, spreadBps, fairValuePctPar, principal, sourceUrl } ],
  excludedCount, divergencePts, divergenceFlag }

No query parameters. A facility belongs to one period, so periodEnd is fixed in the body. There is no availablePeriods.
rows holds included holdings only, sorted by bdcName. excludedCount counts holdings in this facility with no usable mark (null, zero or non-USD principal, or null fair value).
Every facility has at least 2 rows. compare.py only materializes a cluster as a facility when at least 2 of its holdings have a non-null fair_value_pct_par, and facility_summary.lender_count has a CHECK (lender_count >= 2). If the API ever finds fewer than 2 rows it returns 500 DATA_INTEGRITY, and the UI shows the generic error state. There is no "not enough lenders" screen.
divergencePts is max minus min fairValuePctPar over rows. divergenceFlag is AGREEMENT, MILD or FLAGGED (SPEC section 12.8). Both are always non-null.
E6 GET /api/review-queue
[ pair | cluster ]

pair:    { type: "pair", periodEnd, holdingIdA, holdingIdB, rawNameA, rawNameB, score,
           instrumentType, maturityDateA, maturityDateB, spreadBpsA, spreadBpsB,
           sourceUrlA, sourceUrlB }

cluster: { type: "cluster", clusterId, periodEnd, reason: "SAME_BDC_COLLISION",
           holdings: [ { holdingId, bdcName, rawName, instrumentType, maturityDate,
                         spreadBps, sourceUrl } ],
           pairs:    [ { holdingIdA, holdingIdB, score, status } ] }

Pair items are candidate_pairs with status REVIEW. Cluster items come from review_clusters.
A cluster's pairs are the AUTO or CONFIRMED edges that formed it. Each can be rejected through E8, which is how a cluster gets resolved (reject a pair, then re-run compare.py).
Sort: clusters first, then pairs by score descending, then holdingIdA, holdingIdB. Score is shown here. It is hidden only on the labeling page.
E7 and E8
POST /api/review-queue/:idA/:idB/confirm  -> { holdingIdA, holdingIdB, status: "CONFIRMED" }
POST /api/review-queue/:idA/:idB/reject   -> { holdingIdA, holdingIdB, status: "REJECTED" }

Path ids are accepted in either order. The server orders them so holdingIdA < holdingIdB.
E7 is allowed only from REVIEW. E8 is allowed from AUTO, REVIEW or CONFIRMED. Anything else returns 409. Unknown pair returns 404.
Neither changes a curated table, labeled_pairs or any metric. Effects appear after the next compare.py run.
E9 GET /api/metrics
{ precisionAutoOnly:             Range | null,   // headline. Wilson, AUTO band
  precisionReviewBand:           Range | null,   // Wilson, REVIEW band
  precisionIfReviewAutoAccepted: Range | null,   // optional. AUTO + REVIEW, band-weighted, bootstrap
  recallAutoOnly:                Range | null,   // recall given blocking. band-weighted, bootstrap
  recallIfReviewAutoAccepted:    Range | null,   // optional. recall given blocking, bootstrap
  blockingRecall:                Ci | null,      // independent 30-holding check. Wilson on hand-found pairs
  bands: [ { name, bandSize, sampleSize, matchRate: Range } ] | null,
  unsureCount:  number | null,                   // UNSURE labels in the held-out set
  heldOutCount: number | null,                   // labeled held-out pairs
  sensitivityTable: [ { thresholdPts, flaggedCount } ] | null,
  coverage: { bdcs, quarters, holdings, facilities, measuredPeriodEnd } }

Every label-derived field comes from the newest metric_results row and is null until evaluate.py has run. sensitivityTable and coverage are computed live: the table from facility_summary (null when empty), coverage from row counts.
bands[].name is AUTO, REVIEW, JUST_BELOW or LOW. It reports matchRate, the matched share of the band's sample. For AUTO and REVIEW that equals precision. For the two bands below the threshold it is the share of true matches the matcher missed, so do not label it precision.
bands[].bandSize is the size of the band's sampling frame: measured-period candidate pairs minus the tuning pairs, at draw time. sampleSize is how many of them were drawn. The estimates describe that frame, so the tuning pairs are outside it.
Formulas, weighting and interval methods are in SPEC section 12.6. Review-queue confirmations never enter any field: evaluate.py does not read candidate_pairs.status.
thresholdPts is 1, 2 and 5. flaggedCount is the number of facilities with divergencePts >= thresholdPts.
E10 GET /api/filings
[ { bdcName, cik, formType, periodEnd, holdingsCount, sourceUrl } ]

No search parameter. The list is a handful of rows, so the page filters client-side. Sort: periodEnd descending, bdcName ascending.
E11 GET /api/label/next (mounted only when ENABLE_LABELING=true, otherwise 404)
{ sampleId, progress: { labeled, total },
  holdingA: { holdingId, rawName, instrumentType, maturityDate, spreadBps,
              industry, footnotes, crossFilingNames: [string] },
  holdingB: { same keys } }

Returns the next unlabeled sample: TUNING before HELDOUT, then stored draw_order, so ordering leaks nothing about band or score. progress counts the phase being served. 204 when every drawn sample is labeled.
Never includes score, status, band, phase or draw order.
crossFilingNames is the distinct raw names of other holdings, in any ingested filing, whose normalized borrower name equals this holding's, excluding holdings A and B themselves. It uses exact equality of normalized names, computed with the matcher's own normalizer, and no scoring. That makes it independent of scores and bands, but not of normalization, so a spelling variant the normalizer does not unify will not appear. State this limitation in DECISIONS.md and the README.
E12 POST /api/label (same mount rule)
body:     { sampleId, label: "MATCH" | "NO_MATCH" | "UNSURE", labeledBy }
response: { sampleId, label, labeledAt }

Writes labeled_pairs only, as an upsert on sampleId so a mis-keyed label can be corrected. The server copies the holding ids and sets sampling_method (TUNING gives BLOCKED, HELDOUT gives STRATIFIED) and score_band from label_samples. 400 for an invalid label, 404 for an unknown sampleId.
Changes from the earlier E1 to E12 lists
E1: added quarterCount, measuredPeriodEnd. divergenceSplit can be null.
E2: latestPeriodEnd became periodEnd.
E3: list became an object with a borrower header.
E4: added periodEnd. spreadBps is { min, max }.
E5: periodEnd parameter and availablePeriods removed. periodEnd is in the body.
E6: added periodEnd, per-side maturity, spread and sourceUrl. Cluster items gained clusterId and pairs.
E7, E8: transition rules and 409 behaviour defined.
E9: reshaped. precisionAutoPlusReview, precisionRange, recallRange, bootstrapCI, recallGivenBlocking and measured are gone. Bands report matchRate, not precision.
E10: no search parameter.
E11, E12: pairId became sampleId. E11 fields are folded into holdingA and holdingB, and it gained progress. Both are flag-gated.

