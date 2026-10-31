frontend.md: Pages, layouts and API usage
Project: Cross-Lender Private Credit Valuation Monitor. React 19 + Tailwind + React Router (versions pinned on Day 1). Scope and evaluation come from SPEC.md, endpoint shapes from CONTRACT.md. The backend and AI plan is phase_wise.md, and section 2 below is identical in both files.
1. Design rules
Everything is a card. A borrower card opens the borrower. A facility card opens the comparison. A metric card opens its detail. A filing card opens the SEC source.
Left sidebar for navigation. The top bar holds search and a theme toggle only. No settings, no profile, no auth.
(v3) The sidebar now has 7 tabs: Overview, Borrowers, Triage (route `/facilities`), Review, Decisions, Metrics, Filings. Decisions is a new, session-only page (`web/src/decisions.js`, `/decisions`): a local, in-memory log of this browser's own review decisions since the last reload. It is not a database table, starts empty on every reload, and there is no server endpoint that lists past decisions.
Any number taken from a filing links to its SEC source in one click. Aggregates, counts and metrics have no filing source, so they carry no link.
UI text uses plain sentences and simple bullets. Avoid dashes in UI strings, and write ranges as "to".
Null rule: any null from the API renders "Not yet measured". Never show a zero or a placeholder number in place of a null.
(v2) Dossier exception: a row-level dossier field that is null in E5 (costPctPar, fvPctCost, floorBps, pikBps, maturityDate, nonAccrual) renders "Not disclosed", because it means the filing does not state it. Aggregates and fields not yet computed keep "Not yet measured". Never fill a dossier cell in. Cells that differ across lenders are marked with text, not color alone. Exposure always carries the words "Ranking key, not an estimate of loss."
Color is never the only signal. Banners and tags always show their text label.
Every row from a period other than measuredPeriodEnd (from E1) shows a tag, "Outside measured quarter". No metric covers those rows.
No chart library. The one chart is an inline SVG dot plot.
Build order: Borrowers, Facility Comparison, Review Queue, Metrics, then the rest. No polish before the core four work against real endpoints.
The labeling page is dev only: not in the nav, and it appears only when the API has ENABLE_LABELING=true.
2. Endpoints (identical in both files; source: CONTRACT.md)
Shapes, conventions, the error format, the null rule and the write rules live in CONTRACT.md and nowhere else. This section is only the endpoint index, copied from the "Endpoint list" in CONTRACT.md, so both plans name the same endpoints. If an endpoint changes, change CONTRACT.md first, then this table in both files.
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
GET /api/facilities?search=&flag=&sort=
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

Writes: E7 and E8 update candidate_pairs.status. E12 writes labeled_pairs and is mounted only when ENABLE_LABELING=true. Every other endpoint is read-only.
3. App shell and data loading
┌────────────────────────────────────────────────────────────┐
│ ┌────────────┐  ┌──────────────────────────────┐        ◐  │
│ │ VALUATION  │  │ Search borrowers             │           │
│ │ MONITOR    │  └──────────────────────────────┘           │
│ │            │                                             │
│ │ Overview   │            PAGE CONTENT                     │
│ │ Borrowers  │                                             │
│ │ Triage     │                                             │
│ │ Review (n) │   (n = pendingReviewCount from E1)          │
│ │ Decisions  │                                             │
│ │ Metrics    │                                             │
│ │ Filings    │                                             │
│ └────────────┘                                             │
└────────────────────────────────────────────────────────────┘

The shell loads E1 once and shares it through context: the Review badge and measuredPeriodEnd for the "Outside measured quarter" tag. (v3) The sidebar no longer has a "3 BDCs / 1 Quarter" footer; those counts moved to the Overview page's Data coverage card, and a Decisions tab was added. Pages re-fetch E1 after a review action.
Top bar search goes to /borrowers?search=<q> (E2) from every page, not just Borrowers: the placeholder reads "Search borrowers, facilities or lenders". The nav label is Triage; the route stays /facilities and Triage has no search box of its own.
One fetch wrapper in src/api/client.ts. Types in src/api/types.ts mirror CONTRACT.md (hand written, one file). The wrapper parses the error shape and exposes code and message.
Every page uses the same four states: loading skeleton, error with retry, empty, data.
4. Pages
4.1 Overview / (E1)
┌─────────────────────────────────────────────────────────────┐
│ Overview                                                    │
│ Private Credit Monitor                                      │
│ Measured quarter: period end date                           │
│                                                             │
│ ┌───────────────┐ ┌───────────────┐ ┌───────────────┐       │
│ │ BDCs          │ │ Facilities    │ │ Pending       │       │
│ │ (bdcCount)    │ │ (facilityCnt) │ │ Reviews       │       │
│ └───────────────┘ └───────────────┘ └───────────────┘       │
│                                                             │
│ ┌──────────────────────────┐ ┌──────────────────────────┐   │
│ │ Browse Borrowers  →      │ │ Review Queue  →          │   │
│ └──────────────────────────┘ └──────────────────────────┘   │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Valuation Divergence                                    │ │
│ │ Agreement n (x%)  Mild n (x%)  Flagged n (x%)           │ │
│ │                                    View Metrics →       │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

Card links: BDCs opens /filings, Facilities opens /facilities, Pending Reviews opens /review, Divergence opens /metrics.
(v2) One optional extra card shows flaggedExposureUsd from E1 as "Flagged exposure" with the words "Ranking key, not an estimate of loss." A null reads "Not yet measured". It is the first thing cut.
Percentages are computed in the client from the E1 counts. If divergenceSplit is null, the divergence card reads "Not yet measured".
Done when: all counts match the database, the card links work, and the null case renders.
(v3) The built page replaces the two link tiles with 4 stat cards (Facilities, Need review, Flagged exposure, Agreement), each counting up to its value on load. The Valuation Divergence card is now a donut plus a clickable stacked bar (each segment a real link to Facilities, pre-filtered to that flag) alongside a "Biggest differences" ranked list, and a "Data coverage" card (lender, quarter and facility counts, and the measured period end) replaced the old sidebar footer. The three stat cards shown above are the ones that survived; "Flagged exposure" is not cut.
4.2 Borrowers /borrowers (E2)
┌─────────────────────────────────────────────────────────────┐
│ Borrowers                        [ Search borrower... ]     │
│ ┌───────────────────────┐ ┌───────────────────────┐         │
│ │ ACME HOLDINGS         │ │ NOVA INDUSTRIES       │         │
│ │ Period end date       │ │ Period end date       │         │
│ │ 3 Lenders             │ │ 2 Lenders             │         │
│ │ 2 Facilities          │ │ 1 Facility            │         │
│ │ View Borrower →       │ │ View Borrower →       │         │
│ └───────────────────────┘ └───────────────────────┘         │
└─────────────────────────────────────────────────────────────┘

The search box calls E2 with search (debounced, server side). The ?search= query string pre-fills it.
A card from another period shows the "Outside measured quarter" tag.
Empty state: "No borrowers match this search."
Done when: search and deep links work, and the tag shows for non-measured rows.
(v3) Borrowers has no search box of its own any more: the single header search box on every page sends the user here with `?search=`, and this page reads the query string only. The page also adds 3 clickable stat cards (Total borrowers, Across lenders, Flagged) that act as filters, a "Borrowers by status" chart and filter pills (All, Flagged, 2+ lenders), computed client-side from this page's own unfiltered E2 and E4 fetches, not a new field.
4.3 Borrower Detail /borrowers/:id (E3)
┌─────────────────────────────────────────────────────────────┐
│ ← Borrowers                                                 │
│ ACME HOLDINGS                       Period end date         │
│ 3 lenders, 2 facilities                                     │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ First Lien Term Loan                                    │ │
│ │ SOFR, maturity bucket                                   │ │
│ │ 3 lenders                                    View →     │ │
│ └─────────────────────────────────────────────────────────┘ │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Revolver ...                                            │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

The header comes from E3 itself, so a refresh or a direct link works. A 404 shows "This borrower is not in the current build." (borrower ids change when compare.py re-runs.)
Sub-page of Borrowers, not a nav tab.
4.4 Triage (the Facilities page) /facilities (E4)
┌─────────────────────────────────────────────────────────────┐
│ Triage          [ Flagged | All ]   [ Search borrower... ]  │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ ACME HOLDINGS                  FLAGGED, 3.2 points      │ │
│ │ First Lien Term Loan           Exposure USD 1,200,000   │ │
│ │ SOFR, spread 500 to 550 bps    2 signals                │ │
│ │ 3 Lenders                      Widened                  │ │
│ │                                View Comparison →        │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

The default view calls E4 with flag=FLAGGED and sort=exposure. The toggle switches to all facilities (no flag parameter). Search calls E4 with search (matches the borrower name). The spread shows as a min to max range, or one value when min equals max.
Each card shows the borrower, the instrument type, the divergence flag with its points (dollars never replace them), the exposure in USD (ExposureTag, with the words "Ranking key, not an estimate of loss."), the signal count (SignalChip) and a persistence tag (PersistenceTag). persistence is null until F3 is built, and the tag then reads "Not yet measured".
Triage is no longer cuttable. Done when: the default view lists FLAGGED facilities by exposure, the toggle and search work, invalid parameters never reach the API from the UI, and every card shows the flag text with its points.
(v3) The built page is a dashboard plus a table, not a card grid: it calls E4 once with only `sort=exposure` (no flag, no search), and 4 clickable stat tiles plus filter pills (All, Agreement, Review, Flagged, 2+ lenders) slice that one fetched list client-side, so switching filters never refetches. Two bar charts ("Facilities by status" and "Value difference", the latter bucketing the existing `divergencePts` field into fixed ranges) sit above a "Facility directory" table (borrower, lenders, exposure, difference in points, a status dot, and a View link), paged locally with "View all". There is no per-card ExposureTag/SignalChip/PersistenceTag layout, no search box, and no borrower free-text search on this page; use the header search box instead.
4.5 Facility Comparison /facilities/:id (E5), core screen
┌─────────────────────────────────────────────────────────────┐
│ ← Facilities                                                │
│ ACME HOLDINGS                                               │
│ First Lien Term Loan                                        │
│ SOFR, maturity bucket            Period end: date           │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ AGREEMENT or MILD or FLAGGED                            │ │
│ │ 3.2 points of fair value, highest minus lowest lender   │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ Lender Comparison                                           │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ BDC name | Spread bps | FV % of par | Principal | Source│ │
│ │ BDC name | Spread bps | FV % of par | Principal | Source│ │
│ └─────────────────────────────────────────────────────────┘ │
│ Note: N holdings excluded because they have no usable mark. │
│ (only when excludedCount is above 0)                        │
│                                                             │
│ ┌──────────────────────────┐ ┌─────────────────────────┐    │
│ │ Fair Value / Par         │ │ Facility Details        │    │
│ │ one dot per lender       │ │ Instrument, rate,       │    │
│ │ (inline SVG)             │ │ maturity bucket         │    │
│ └──────────────────────────┘ └─────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘

There is no period selector. A facility belongs to one period, so the period is just a label.
The banner has three states, always showing the label and the point spread.
The Source cell opens sourceUrl in a new tab. Every row has one.
Every facility has at least 2 rows. If the API returns an error (including DATA_INTEGRITY), show the generic error state with retry. There is no "not enough lenders" screen.
Done when: all three banner states render with text, the source links open the right filing, the excluded note appears only when excludedCount is above 0, and the dot plot has one dot per row.
(v2) Facility Comparison gains, all from E5 and all keeping the source link on every number: an exposure line under the banner (exposureUsd, with "Ranking key, not an estimate of loss."); an Evidence panel, which is the lender table extended with cost % of par, fair value % of cost, spread, floor, PIK, maturity and non-accrual (a null dossier cell reads "Not disclosed", and cells that differ across lenders are marked with text, not color alone); signal chips with labels for the codes in signals (NON_ACCRUAL, PIK_DIFFERS, FLOOR_DIFFERS, SPREAD_DIFFERS, MATURITY_DIFFERS, COST_BASIS_GAP, RATE_TYPE_DIFFERS), worded as signals present, never as causes; and, if F3 is built, a History strip (HistoryStrip, inline SVG like DotPlot: prior to current dots per lender, plus the persistence label). history is null when F3 is not built and reads "Not yet measured"; when F3 is built and there are fewer than two linked prior marks, persistence is NO_PRIOR. Done when: the evidence panel shows a dossier null as "Not disclosed" and the chips render with text.
(v3) The built page is 3 compact cards, not the v2 Evidence panel: "Current reported value" (one zoomed bar per lender, `LenderValueBars`, plus the point spread and, if `signals` is non-empty, a one-line "Why the values may differ" sentence), "Loan details" (loan type, interest rate, maturity bucket, reporting period) and "Lender reports" (each lender's current value and loan amount, with the prior quarter's value shown inline as "Previous -> Current" when a history link exists, and the excluded-holdings note when `excludedCount` is above 0). There is no sortable table, no per-row expand, no dossier fields (cost % of par, FV % of cost, floor, PIK, non-accrual) and no History strip or persistence tag on screen; E5 still returns all of it, nothing here is a backend change.
4.6 Review Queue /review (E6, E7, E8)
┌─────────────────────────────────────────────────────────────┐
│ Review Queue                                  12 Pending    │
│ Decisions apply after the next compare run.                 │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ CLUSTER NEEDS REVIEW                                    │ │
│ │ Two holdings from the same BDC landed in one cluster    │ │
│ │ Holdings: name, BDC, maturity, spread, source           │ │
│ │ Pairs that formed it:                                   │ │
│ │   A and B   score 0.95  AUTO       [ Reject ]           │ │
│ │   B and C   score 0.93  AUTO       [ Reject ]           │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ ACME HOLDINGS LLC   ↔   ACME HOLDCO INC     Score 0.86  │ │
│ │ First Lien, maturity A and B, spread A and B, sources   │ │
│ │              [ Confirm ] [ Reject ] [ Skip ]            │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

Clusters come first, then pairs by score, as the API sorts them.
Confirm calls E7, Reject calls E8. The card leaves the list on success, and E1 is re-fetched to update the badge.
On a 409 (the pair changed status), show "This pair was already decided." and refresh the list.
Skip is local only: it hides the card for this session with no API call.
Cluster cards offer Reject only, on each pair that formed the cluster. Resolving a cluster means rejecting a pair, then re-running compare.py.
(v3) The built page shows one case at a time (Previous/Next paging across all items, clusters and pairs mixed in the API's own order) instead of listing every card, with 4 stat tiles (Need review, Possible match, Group issues, Completed) and two progress cards above it. Cluster cards also offer "Same" on each record alongside Reject: "Same" makes no API call (the pair is already AUTO or CONFIRMED, so leaving it alone already means "same") and is logged to the Decisions page with status ACKNOWLEDGED, not CONFIRMED. There is no Skip button any more; a pair card's two actions are "Same borrower" (Confirm) and "Not the same" (Reject). Every decision, including "Same", is recorded to a new in-memory log (`web/src/decisions.js`) shown on the new Decisions page (`/decisions`), which is not a server endpoint and does not persist across a reload.
4.6a Decisions /decisions (no endpoint of its own; reads the session's own E7/E8 results)
A new page, not in the original plan. Shows 4 stat cards (Decisions logged, Same borrower/Accepted, Not the same/Separated, Left as is) and a table of every decision this browser has sent since the last reload (when, case name, Possible match or Group issue, and the decision). A "Clear log" button empties it. There is nothing server-side to load: the table is built entirely from what `recordDecision()` has collected locally after each successful E7/E8 call, or after a Group issue "Same" action that makes no call at all. It must never be described as a database table or an audit trail other browsers or devices can see.
The score is shown here. It is hidden only on the labeling page.
Done when: both card types render, Confirm and Reject update the list and the badge, the 409 case is handled, and the page states that decisions apply after the next compare run.
4.7 Metrics /metrics (E9)
┌─────────────────────────────────────────────────────────────┐
│ Metrics                                                     │
│ ┌────────────┐ ┌──────────────┐ ┌────────────┐ ┌──────────┐ │
│ │ Precision  │ │ Precision    │ │ Recall     │ │ Blocking │ │
│ │ AUTO only  │ │ REVIEW band  │ │ given      │ │ recall   │ │
│ │ (headline) │ │              │ │ blocking   │ │ (30 held)│ │
│ └────────────┘ └──────────────┘ └────────────┘ └──────────┘ │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ How UNSURE labels are counted                           │ │
│ │ If UNSURE counts as no match: value (95% CI low to high)│ │
│ │ If UNSURE counts as match:    value (95% CI low to high)│ │
│ │ Raw UNSURE count: N     Held out pairs: N               │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ If REVIEW pairs were auto accepted (optional)           │ │
│ │ Precision and recall, same two lines as above           │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Per band: AUTO, REVIEW, Just below, Low                 │ │
│ │ Band size | Sample | Match rate | 95% CI                │ │
│ └─────────────────────────────────────────────────────────┘ │
│                                                             │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Divergence sensitivity                                  │ │
│ │ 1 pt: n flagged   2 pts: n flagged   5 pts: n flagged   │ │
│ └─────────────────────────────────────────────────────────┘ │
│ Coverage: BDCs, quarters, holdings, facilities, measured    │
│ quarter. Recall is given blocking. Metrics cover the        │
│ measured quarter only.                                      │
└─────────────────────────────────────────────────────────────┘

Each headline card shows the two UNSURE values as "low to high" sorted by value. For recall the UNSURE-as-match value is the lower one, so sort, do not rely on field order.
Every number has its 95% interval next to it, from the same Range object.
Any null field reads "Not yet measured", on its own. Fields become available on different days.
The band table reports "Match rate", not precision. For the two bands below the threshold it is the share of true matches the matcher missed.
No figure on this page includes review-queue confirmations, and the page says so in one line.
Done when: every card renders both its value and its null state, and the sensitivity table and coverage render from live data.
(v2) New Metrics cards from E9, descriptive and report-only: the signal lift table (evidenceLift: for each signal the share of FLAGGED against the share of AGREEMENT facilities, with both n), the unexplained share (FLAGGED facilities with no signal) and field coverage per BDC (fieldCoverage). If F3 is built, link accuracy with its interval (historyLinks). Each card reads "Not yet measured" when null, and the page says "signals present, not causes" in one line.
(v3) The built page defaults to a compact dashboard (4 tiles: Match quality, Found matches, Search found, Labelled cases; two bar charts; a Test results card) with a button reading "Show full statistical detail" ("Hide full statistical detail" once open). Everything in this mockup and the v2 paragraph above, every interval, band table, the out-of-time section and the sensitivity table, is unchanged in content and wording; it only moved behind that toggle so the dashboard is the default view.
4.8 Filings /filings (E10)
┌─────────────────────────────────────────────────────────────┐
│ SEC Filings                       [ Filter filings... ]     │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ Apollo Debt Solutions BDC                               │ │
│ │ 10-Q, period end date                                   │ │
│ │ Holdings: n                  View SEC Filing ↗          │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘

The filter box filters the loaded list in the browser (E10 has no search parameter).
(v3) The built page adds, both computed client-side from E10's own rows (no new field, no new endpoint): a "Filings coverage" lender-by-quarter matrix (checkmark present, circle not yet filed, with a complete count per quarter) and a "Latest filings" list (top 5 by period end) linking back to the table. Clicking a table row selects it and shows a detail card (filed date, type, status, holdings count, the SEC filing link). The status column in the table itself is always "Processed": E10 has no issue state in the data, only present or absent.
4.9 Labeling /label (dev only, not in nav) (E11, E12)
┌─────────────────────────────────────────────────────────────┐
│ Label pair                               Progress n / total │
│ ┌──────────────────────┐ ┌──────────────────────┐           │
│ │ Holding A            │ │ Holding B            │           │
│ │ raw name             │ │ raw name             │           │
│ │ instrument, maturity │ │ instrument, maturity │           │
│ │ spread               │ │ spread               │           │
│ │ industry             │ │ industry             │           │
│ │ footnotes            │ │ footnotes            │           │
│ │ other filing names   │ │ other filing names   │           │
│ └──────────────────────┘ └──────────────────────┘           │
│ [ M Match ] [ N No match ] [ U Unsure ]                     │
│ A MATCH needs one independent signal, otherwise choose      │
│ Unsure. Principal size is not evidence.                     │
└─────────────────────────────────────────────────────────────┘

Never shows score, status, band or phase, because E11 never sends them.
The other filing names list matches exact normalized names only, so it can miss a spelling variant. Read the raw names too, and do not treat an empty list as evidence.
Keys M, N and U call E12 and then load the next sample. The client keeps the last 5 samples in memory, so a mis-keyed label can be corrected by re-sending E12 for that sampleId.
A 404 shows "Labeling is turned off on this server." A 204 shows "Every drawn sample is labeled."
Plain and fast. No styling beyond readability.
4.10 Landing page (optional, last)
Only after the core four, the remaining pages, the README and DECISIONS.md are done. Layout and style ideas may come from the Webflow reference. The content must come from the project's own problem statement and non-claims: what the gap is, where the data comes from (SEC BDC filings, including Apollo's), what is measured, what is not claimed, and a button into the app. The five-line glossary from the README (BDC, syndicated loan, fair value, par, mark) belongs on this page for non-finance readers. Copy it from the README so the two stay in sync. Do not carry over the template's pricing, testimonials, user counts or security claims, and do not copy its assets, since it is a licensed template.
5. Route map
Landing (optional)
  App
    Overview            /
    Borrowers           /borrowers
      Borrower Detail   /borrowers/:id
    Facilities (nav: Triage) /facilities
      Comparison        /facilities/:id
    Review Queue        /review
    Decisions           /decisions
    Metrics             /metrics
    Filings             /filings
    Labeling (dev)      /label

(v3) Decisions was added above; the landing page was not built, so `/` is the Overview page directly.

6. Page to endpoint map
Page
Endpoints
Writes
Shell
E1
none
Overview
E1
none
Borrowers
E2, E4 (unfiltered, for client-side status)
none
Borrower Detail
E3
none
Facilities
E4
none
Facility Comparison
E5
none
Review Queue
E6, E7, E8, E1 (badge)
E7, E8
Decisions
none (reads this browser's own past E7/E8 results from memory)
none
Metrics
E9
none
Filings
E10
none
Labeling
E11, E12
E12

7. Shared components
Card, StatCard, Banner (label plus point spread), SourceLink, PeriodTag ("Outside measured quarter"), RangeStat (renders a Range with intervals, or "Not yet measured"), DotPlot (inline SVG), BandTable, PairCard, ClusterCard, EmptyState, ErrorState (with retry), Skeleton. (v2) ExposureTag, SignalChip, EvidenceTable, HistoryStrip (inline SVG, same approach as DotPlot) and PersistenceTag. No chart library.
(v3) `DotPlot`, `Banner`, `ExposureTag`, `SignalChip`, `EvidenceTable`, `HistoryStrip` and `PersistenceTag` are all still defined in `web/src/components.jsx` but are no longer used by any page; the redesign replaced them with `DivergenceDonut`, `ClickableDivergenceBar`, `BarList`/`DivergenceSplitChart`, `RankedShareList`, `LenderValueBars` and `RangeBar` (all inline SVG or CSS, still no chart library), plus `StatusPill`/`StatusDot` for the flag colors and `Toast` for the "Decision saved" confirmation. `recordDecision`/`getDecisions`/`clearDecisions` (`web/src/decisions.js`) back the new Decisions page.
8. Build order by day (matches SPEC section 18)
Day
Frontend work
Depends on
2
Vite and TypeScript scaffold, router, layout, bare table
temporary dev route and E10
3
types.ts and client.ts from the frozen contract
CONTRACT.md
6 AM
Labeling page
E11, E12
7
Core four against real endpoints: Borrowers, Borrower Detail, Facility Comparison, Review Queue skeleton
E1 to E8
9
Metrics, cluster cards and 409 handling in Review, comparison polish
E9, final compare.py
10
Triage view (the Facilities page), Evidence panel, new Metrics cards, Overview, Filings, the null and error states everywhere, optional landing page
E1, E4, E10

If the schedule slips, cut in this order: landing page, Filings, Overview, Borrower Detail polish. Triage (the Facilities page), Review Queue, Comparison and Metrics never get cut.
9. Frontend rules for Claude Code
You know React, so review every diff and be able to walk through the data flow for the comparison page and the metrics page without notes.
Build against the real API from Day 7. Do not build from invented sample numbers, and never screenshot made-up data.
types.ts mirrors CONTRACT.md exactly. If the contract changes, change it there first.
Spot-check 10 displayed numbers against the actual SEC filing by clicking their source links.

