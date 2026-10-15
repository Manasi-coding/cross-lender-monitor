Cross-Lender Private Credit Valuation Monitor — MASTER DOC v2
Reference this document throughout build and test. Numbers marked "default" are starting points to tune from real data on Day 8, not final answers.
Document map. SPEC.md (this file) owns scope, schema, evaluation method, tests and schedule. CONTRACT.md owns the API (E1 to E12) and is the only place endpoint shapes are defined. phase_wise.md and frontend.md carry only an endpoint index copied from it. phase_wise.md is the build sequence and frontend.md is the UI plan. Where either disagrees with SPEC.md or CONTRACT.md, those two win.

1. Problem Statement
Private credit loans are frequently syndicated — a single borrower's loan is held across multiple lenders. Business Development Companies (BDCs), public vehicles that make these loans, must file a "Consolidated Schedule of Investments" with the SEC every quarter (10-Q/10-K): every holding, with issuer name, industry, instrument type, interest rate structure, maturity, principal, cost, and fair value (the lender's own internally-determined mark).
No shared identifier exists across BDC filers. The same borrower appears under inconsistently formatted names in different BDCs' schedules. Each BDC's fair value is an independent, internally-produced number — there is no public way to see, today, whether two real lenders agree on the value of the same credit.
This is a verified, current, named industry gap: in 2026, ICE launched ICE IDs for private credit under ICE Private Credit Intelligence, with Apollo named as ICE's anchor partner (confirmed directly from ICE's press release and platform page). ICE IDs are assigned at origination, from deal documents — a forward-looking fix. This project instead resolves identity retroactively, from already-public filings — a different, complementary problem shape, not a claim to replicate ICE's process.
2. Solution Overview
Ingest real SEC filings from 3 BDCs (Apollo's own Apollo Debt Solutions BDC — CIK 1837532 — plus 2 others chosen by actual borrower overlap), build a canonical borrower/facility registry via a measured entity-resolution pipeline, and compute cross-lender fair-value comparisons at the facility level, expressed as % of par, flagged by a defensible divergence threshold.
Non-claims (state explicitly in the README): not a reconstruction of Apollo's internal valuation process; not a claim that ICE IDs are being reverse-engineered; not a claim of market-wide coverage — 3 BDCs and one measured quarter only.
Measured set. One common quarter-end across all 3 BDCs (MEASURED_PERIOD_END, set once in .env and read by both the pipeline and the API) is the measured set. Tuning labels, held-out labels, band sizes and every reported metric come from candidate pairs of that quarter only. If a second quarter is ingested, its borrowers and facilities appear as separate rows with their own period label and carry no cross-quarter claim: nothing links a facility across quarters and no metric covers that quarter. Cross-period linking is a new, unmeasured step and is listed as future work (§14).

3. The Application
3.1 Actors
Analyst (end user): searches borrowers, views facility-level cross-lender comparisons, works the review queue.
System: batch pipeline — ingest → normalize → block → score → classify → persist. No human in the automated path; humans only touch the review queue.
3.2 What the User Sees — screen-by-screen
Borrower Search — search box; result rows show canonical borrower name, period label, # lenders, # facilities.
Facility Comparison (core screen) — header (borrower, period end, instrument type, reference rate, maturity bucket); table of one row per contributing BDC (name, total spread bps, fair value % of par, principal, source filing URL); divergence banner (AGREEMENT/MILD/FLAGGED) with the actual point spread shown. There is no period selector: a facility belongs to one period. Every facility has at least 2 lenders with a usable mark; holdings excluded for missing, zero or non-USD principal, or an unfunded commitment, appear only as a count in a note.
Review Queue — one row per candidate pair awaiting a decision (see §6 candidate_pairs): raw names side by side, score, instrument type, maturity, spread. Actions: Confirm Match / Reject / Skip. Review clusters (two holdings from one BDC landing in the same cluster) get their own card listing the holdings and the AUTO or CONFIRMED pairs that formed it, each with a Reject action; resolving a cluster means rejecting a pair and re-running compare.py. Decisions apply only after the next compare.py run.
Metrics / Evaluation — AUTO-only precision (headline) and REVIEW band precision, each with a Wilson interval and an UNSURE range (UNSURE as NO_MATCH and as MATCH); optional precision if REVIEW pairs were auto-accepted, labeled exactly that; recall given blocking with a bootstrap interval; blocking recall from the independent 30-holding check (§12.5); raw UNSURE count; divergence sensitivity table (1/2/5pt); coverage counts. Anything not yet computed reads "Not yet measured".
3.3 What Is Deliberately Out of Scope
Real-time ingestion; Kafka/Spark; full market coverage (~40–50 public BDCs); more than one measured quarter; cross-period facility linking and any cross-quarter claim; equity and unfunded-commitment positions; authentication/user accounts; Spring Boot.
3.4 Frontend Build Priority
Borrower Search → Facility Comparison → Review Queue → Metrics. A reviewer looks, in order: is the data real and sourced (source URLs), is the matching claim measured (metrics), is ambiguity handled honestly (review queue), does it look finished (comparison view polish, last).
After the core four, and the first things cut: the Overview, Facilities and Filings pages (E1, E4, E10) and the optional landing page. The labeling page (E11, E12) is separate: it is required for the evaluation, so it is built on Day 6, but it is dev-only and unstyled beyond what labeling needs.

4. Technologies and Tech Stack
4.1 Stack
Python 3.11 (pandas, rapidfuzz) — pipeline. Node 24 LTS + Express 5 (TypeScript) — API. React 19 + Tailwind — UI. PostgreSQL 16. pytest + API tests. GitHub Actions. Docker Compose v2.
4.2 Technology Rules
Pipeline is a standalone Python process (CLI entry point), never imported into the Node process.
API is read-mostly, not read-only. Two kinds of writes exist, both listed in CONTRACT.md: the review-queue actions (E7, E8), which update candidate_pairs.status only; and the labeling action (E12), which writes labeled_pairs only and exists only when ENABLE_LABELING=true (default false, since there is no auth). Every other endpoint only reads. State it this way in the README.
No ORM. Explicit parameterized SQL in both Python and Node, inspectable without tracing a layer.
All tunable values live in one config.yaml/config.py.
source_url is carried through every layer, never dropped in a join.
4.3 Pinned Version Matrix
Component
Version
Note
Python
3.11.x


pandas
2.x


rapidfuzz
3.x


Node
24 LTS (or 22 LTS)
Node 20 is EOL
Express
5.x
fallback to 4.x only if Day 1 finds a blocking incompatibility
TypeScript
5.x


React
19.x
fallback to 18.x only if Day 1 finds a blocking incompatibility
PostgreSQL
16.x


Docker Compose
v2 schema


Tailwind CSS
pin on Day 1


React Router
pin on Day 1
needed for the route map in frontend.md
Data fetching library
pin on Day 1
optional, plain fetch is acceptable

4.4 Dependency Rules
Lockfiles with pinned hashes; no latest Docker tags; .env.example committed, .env gitignored.
4.5 Known Conflict Traps
companyfacts API drops dimensional facts → parse Inline XBRL directly. Fiscal year-end mismatch across BDCs → hard-filter same period-end (usually won't shrink the set much, since most BDCs report on calendar quarter-ends — verify Day 1). Floating-rate strings → parse into (reference_rate, spread_bps, floor_bps), never string-compare. PIK components → capture cash + PIK, compare total spread. Dev/CI version drift → pin identically everywhere.
4.6 Day-1 Verification Checklist (strict order)
Parse one Apollo ADS Inline XBRL filing end-to-end.
Confirm CIK 1837532 directly on EDGAR.
Set SEC User-Agent header; confirm no 403s.
Pick 2 more BDCs by actual borrower-name overlap under the period-end filter, and record the one common quarter-end all 3 report (MEASURED_PERIOD_END in .env).
Run the actual Node/Express/React version + compatibility check. Gate: if XBRL parsing fails by end of Day 2, shrink scope.
4.7 Reference Snippets
EDGAR filing index: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=0001837532&type=10-Q. Required header: User-Agent: <name> <email>. Stay well under 10 req/s with backoff regardless.

5. Architecture
SEC EDGAR (Inline XBRL filings)
        │
        ▼
[Python] ingest.py  ──►  raw_filings, raw_holdings            (raw layer)
        │
        ▼
[Python] normalize.py, block.py, match.py
        ──►  normalized_holdings, blocking_keys,
             candidate_pairs (AUTO/REVIEW/NO_MATCH/CONFIRMED/REJECTED)          (staged)
        │
        ▼
[Python] compare.py  ──►  canonical_borrowers, canonical_facilities, holding_facility_map,
                          facility_comparisons, facility_summary,
                          review_clusters, review_cluster_members                (curated, full rebuild)
        │
        ▼
[Node/Express] read-mostly API  (writes: candidate_pairs.status via E7/E8; labeled_pairs via E12 when ENABLE_LABELING=true)
        │
        ▼
[React] UI

Facilities are built from AUTO-scored pairs plus CONFIRMED pairs via connected-components clustering on the pair graph, with these constraints (required, not optional — naive connected components will merge wrongly otherwise):
Only pairs from different BDCs are ever scored or clustered. Two holdings from the same filing/BDC must never merge — a borrower's term loan and revolver in one BDC's own schedule are distinct facilities, never variants of "the same" cross-lender match.
REJECTED pairs are cannot-link constraints, not just ignored edges — if A–B is REJECTED, no clustering path may merge A and B even transitively through some C. Process edges CONFIRMED first, then by descending score (ties by ascending holding ids), and skip any edge whose union would join a cannot-link pair, logging each skip.
If a resulting cluster contains two holdings from the same BDC, route the whole cluster to the review queue instead of forming a facility — this catches A–B and B–C each being individually valid while A–B–C together implies an invalid same-BDC merge.
What compare.py builds, in order (a full deterministic rebuild in one transaction, so the API never sees partial state):
Cluster AUTO plus CONFIRMED pairs under the three constraints above. Clusters with a same-BDC collision go to review_clusters, not to facilities.
A cluster becomes a facility only if at least 2 of its holdings have a non-null fair_value_pct_par. Holdings with a null value stay in facility_comparisons, flagged excluded, and are counted in excluded_count. A cluster that fails this test is not a facility. This is what guarantees every facility has lender_count >= 2, so a facility with fewer than 2 lenders is a data error and never a UI state.
Name each cluster by the most frequent borrower_normalized among all its holdings, ties broken by ascending codepoint order. Digits stay in names.
Group facilities into borrowers by exact equality of that cluster name within one period. A borrower with a single facility is still its own borrower. Two clusters of the same real borrower that normalize differently become two borrowers. This step is not covered by the labeled evaluation: list it as an unmeasured step in the limitations and never fold it into matcher precision.
Facility attributes: instrument_type_norm is shared by construction (blocking requires an exact match). reference_rate is the most frequent member value (ties ascending). maturity_bucket is the earliest member maturity (default).
Divergence per facility is max minus min fair_value_pct_par over included holdings, in points of par (§12.8).
A facility belongs to exactly one period, because pairs are only scored within one period end and nothing links a holding across periods. Borrower, facility and cluster IDs are regenerated on every rebuild: stable across page loads, not across a compare.py run.
Idempotency: raw_filings.accession_number is UNIQUE — re-ingesting an already-loaded filing is a no-op (tested, §13 #6).

6. Database Schema
-- RAW LAYER
CREATE TABLE raw_filings (
  filing_id        SERIAL PRIMARY KEY,
  cik               TEXT NOT NULL,
  bdc_name          TEXT NOT NULL,
  form_type         TEXT NOT NULL,
  period_end_date   DATE NOT NULL,
  filing_date       DATE NOT NULL,
  accession_number  TEXT NOT NULL UNIQUE,
  source_url        TEXT NOT NULL,
  ingested_at       TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE raw_holdings (
  holding_id             SERIAL PRIMARY KEY,
  filing_id              INT REFERENCES raw_filings(filing_id),
  portfolio_company_raw  TEXT,
  industry_raw           TEXT,
  instrument_type_raw    TEXT,
  interest_rate_raw      TEXT,
  maturity_date_raw      TEXT,
  principal_raw          TEXT,
  principal_unit_raw     TEXT,              -- the unit tag on the principal fact, as parsed (u_EUR, u_USD ...); added Day 2
  cost_raw               TEXT,
  fair_value_raw         TEXT,
  footnotes_raw          TEXT,
  row_order              INT,
  source_url             TEXT NOT NULL      -- carried on every holding row, copied from raw_filings; added Day 2
);

-- STAGED LAYER
CREATE TABLE normalized_holdings (
  holding_id            INT PRIMARY KEY REFERENCES raw_holdings(holding_id),
  bdc_cik               TEXT NOT NULL,
  period_end_date       DATE NOT NULL,
  borrower_normalized   TEXT NOT NULL,
  industry              TEXT,               -- carried through: used as INDEPENDENT labeling evidence (§12), not matcher input
  instrument_type_norm  TEXT NOT NULL,
  reference_rate         TEXT,
  spread_bps             NUMERIC,
  floor_bps              NUMERIC,
  pik_bps                NUMERIC DEFAULT 0,
  maturity_date          DATE,
  principal              NUMERIC,
  principal_currency     TEXT,
  cost                   NUMERIC,
  fair_value             NUMERIC,
  fair_value_pct_par     NUMERIC,           -- NULL if principal IS NULL OR principal = 0 OR principal_currency <> 'USD' — guarded, never divide by zero
  footnotes              TEXT,              -- independent labeling evidence
  source_url             TEXT NOT NULL
);

CREATE TABLE blocking_keys (
  holding_id   INT REFERENCES normalized_holdings(holding_id),
  block_key    TEXT NOT NULL
);

-- CANDIDATE PAIRS: every holding-pair the matcher scored, independent of final facility assignment
CREATE TABLE candidate_pairs (
  holding_id_a  INT REFERENCES normalized_holdings(holding_id),
  holding_id_b  INT REFERENCES normalized_holdings(holding_id),
  score         NUMERIC NOT NULL,
  status        TEXT NOT NULL,     -- AUTO | REVIEW | NO_MATCH | CONFIRMED | REJECTED
  updated_at    TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (holding_id_a, holding_id_b),
  CHECK (holding_id_a < holding_id_b)
);
-- store EVERY scored pair, including below-0.80 (status NO_MATCH) — you need these
-- to draw the precision/recall curve at other thresholds, not just report the chosen one.
-- The CHECK enforces one canonical ordering so a pair is never duplicated in both directions.

-- CURATED LAYER (rebuilt in full, in one transaction, by compare.py; see §5)
CREATE TABLE canonical_borrowers (
  canonical_borrower_id SERIAL PRIMARY KEY,
  canonical_name        TEXT NOT NULL,        -- exact normalized cluster name (§5 step 3)
  period_end_date       DATE NOT NULL,
  created_at            TIMESTAMPTZ DEFAULT now(),
  UNIQUE (canonical_name, period_end_date)
);

CREATE TABLE canonical_facilities (
  facility_id            SERIAL PRIMARY KEY,
  canonical_borrower_id  INT NOT NULL REFERENCES canonical_borrowers(canonical_borrower_id),
  period_end_date        DATE NOT NULL,
  instrument_type_norm   TEXT NOT NULL,
  reference_rate         TEXT,
  maturity_bucket        DATE                 -- earliest member maturity (default)
);

CREATE TABLE holding_facility_map (
  holding_id    INT PRIMARY KEY REFERENCES normalized_holdings(holding_id),   -- a holding is in at most one facility
  facility_id   INT NOT NULL REFERENCES canonical_facilities(facility_id)
  -- built from candidate_pairs where status IN ('AUTO','CONFIRMED') via clustering, never a separate source of truth
);

-- One row per holding in a facility: a snapshot of exactly what was compared.
-- Excluded holdings are kept and flagged.
CREATE TABLE facility_comparisons (
  facility_id         INT NOT NULL REFERENCES canonical_facilities(facility_id),
  holding_id          INT NOT NULL REFERENCES normalized_holdings(holding_id),
  period_end_date     DATE NOT NULL,
  bdc_cik             TEXT NOT NULL,
  bdc_name            TEXT NOT NULL,
  spread_bps_total    NUMERIC,                -- spread_bps + pik_bps
  principal           NUMERIC,
  fair_value_pct_par  NUMERIC,                -- NULL when excluded
  excluded_reason     TEXT,                   -- NULL | ZERO_OR_NULL_PRINCIPAL | NULL_FAIR_VALUE | NON_USD_PRINCIPAL | UNFUNDED_COMMITMENT
  source_url          TEXT NOT NULL,
  PRIMARY KEY (facility_id, holding_id)
);

-- One row per facility
CREATE TABLE facility_summary (
  facility_id      INT PRIMARY KEY REFERENCES canonical_facilities(facility_id),
  lender_count     INT NOT NULL CHECK (lender_count >= 2),   -- holdings with a usable mark
  excluded_count   INT NOT NULL,
  divergence_pts   NUMERIC NOT NULL,          -- max minus min fair_value_pct_par over included holdings
  divergence_flag  TEXT NOT NULL              -- AGREEMENT | MILD | FLAGGED (cutoffs in §12.8)
);

CREATE TABLE review_clusters (
  cluster_id       SERIAL PRIMARY KEY,
  period_end_date  DATE NOT NULL,
  reason           TEXT NOT NULL              -- SAME_BDC_COLLISION
);
CREATE TABLE review_cluster_members (
  cluster_id  INT NOT NULL REFERENCES review_clusters(cluster_id) ON DELETE CASCADE,
  holding_id  INT NOT NULL REFERENCES normalized_holdings(holding_id),
  PRIMARY KEY (cluster_id, holding_id)
);

-- EVALUATION TABLES
-- Both sampling phases draw only candidate pairs from the measured period (MEASURED_PERIOD_END).

-- Singleton: the current matcher freeze. Written by `config --freeze`, deleted by `config --unfreeze` (§12.6).
-- matcher_config_hash covers the normalization, blocking, scoring and bands config sections plus the
-- source files listed in freeze.hashed_files. The name is kept short; it is a hash of the matcher, not only of config.
CREATE TABLE matcher_freeze (
  freeze_id            INT PRIMARY KEY DEFAULT 1 CHECK (freeze_id = 1),
  matcher_config_hash  TEXT NOT NULL,
  git_sha              TEXT,
  frozen_at            TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE label_samples (
  sample_id     SERIAL PRIMARY KEY,
  holding_id_a  INT NOT NULL REFERENCES normalized_holdings(holding_id),
  holding_id_b  INT NOT NULL REFERENCES normalized_holdings(holding_id),
  phase         TEXT NOT NULL,                -- TUNING | HELDOUT
  score_band    TEXT,                         -- AUTO | REVIEW | JUST_BELOW | LOW; HELDOUT only, assigned from candidate_pairs.score at draw time
  draw_order    INT NOT NULL,                 -- random permutation; E11 serves in this order so order leaks nothing
  drawn_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE (holding_id_a, holding_id_b, phase),
  CHECK (holding_id_a < holding_id_b)
);

CREATE TABLE band_sizes (
  score_band           TEXT PRIMARY KEY,      -- AUTO | REVIEW | JUST_BELOW | LOW
  band_size            INT NOT NULL,          -- sampling frame size in this band: measured-period candidate pairs minus the tuning pairs, at draw time (the N_b in §12.6)
  sample_size          INT NOT NULL,
  matcher_config_hash  TEXT NOT NULL,         -- equals matcher_freeze.matcher_config_hash at draw time
  drawn_at             TIMESTAMPTZ DEFAULT now()
);

-- GROUND TRUTH: kept separate from candidate_pairs/UI actions — clicking Confirm in the review queue
-- is NOT the same as a labeled ground-truth row. Never merge these two tables or use one to populate the other.
CREATE TABLE labeled_pairs (
  pair_id          SERIAL PRIMARY KEY,
  sample_id        INT NOT NULL UNIQUE REFERENCES label_samples(sample_id),
  holding_id_a     INT NOT NULL,
  holding_id_b     INT NOT NULL,
  label            TEXT NOT NULL,          -- MATCH | NO_MATCH | UNSURE
  labeled_by       TEXT NOT NULL,
  labeled_at       TIMESTAMPTZ DEFAULT now(),
  sampling_method  TEXT NOT NULL,          -- BLOCKED (tuning) | STRATIFIED (held-out)
  score_band       TEXT                    -- copied from label_samples for held-out rows, see §12.6
);

CREATE TABLE blocking_recall_checks (
  check_id                SERIAL PRIMARY KEY,
  holding_id              INT NOT NULL REFERENCES normalized_holdings(holding_id),  -- picked at random, independent of blocking
  counterpart_holding_id  INT NOT NULL REFERENCES normalized_holdings(holding_id),  -- found by hand in another BDC's schedule
  found_by_blocking       BOOLEAN NOT NULL,                                         -- did blocking put both in one block
  checked_at              TIMESTAMPTZ DEFAULT now()
);
-- Only holdings for which you found a true counterpart get a row.

CREATE TABLE metric_results (
  metric_id            SERIAL PRIMARY KEY,
  computed_at          TIMESTAMPTZ DEFAULT now(),
  matcher_config_hash  TEXT NOT NULL,
  payload              JSONB NOT NULL         -- every label-derived E9 field; sensitivityTable and coverage are computed live by the API
);

Guard, mandatory: fair_value_pct_par computation must check principal IS NOT NULL AND principal != 0 AND principal_currency = 'USD' and the row is not flagged by the filer's unfunded-commitment footnote pattern (configured per filer) before dividing; otherwise store NULL and exclude the row from comparisons (never silently produce Infinity/error).

7. API Contract
The API contract (E1 to E12, response shapes, error format, null rule, write rules) lives in CONTRACT.md and nowhere else. Do not copy shapes into this file. Test 12 and the shape tests in §13 check against CONTRACT.md.
Write surface, for the README: E7 and E8 update candidate_pairs.status; E12 writes labeled_pairs and is mounted only when ENABLE_LABELING=true. A Confirm or Reject changes no curated table until compare.py is re-run.

8. Core USPs
Measured (not asserted) matching, evaluated against independent evidence, not the matcher's own features. Facility-level, tolerance-aware comparison (% of par, never dollars, guarded against null/zero principal). Full auditability — every number traces to a real source_url. Explicit ambiguity handling via a candidate-pairs review queue, kept separate from ground truth. Grounded in a verified, current, named industry initiative, with the retroactive-vs-origination distinction stated plainly.
9. Why This Is Attractive for SDE Roles
Real messy data engineering + a classic hard CS problem (entity resolution) solved with a non-circular, measured evaluation + backend API design + full-stack delivery, on an undisputable public dataset.

10. Features
10.1 MVP (must ship)
Ingest 3 BDCs for one measured quarter (a second quarter may be ingested but is unmeasured), same-period-end filter. Normalize → block → rapidfuzz score → candidate_pairs with AUTO/REVIEW/NO_MATCH. Facility-level comparison, % of par, null/zero-principal guarded. Divergence classification with the 1/2/5pt sensitivity table. Review queue (pairs: Confirm/Reject on candidate_pairs; clusters: Reject on their constituent pairs). Source URL on every displayed row. Docker Compose one-command start. CI running all tests.
10.2 Core (don't skip for polish)
Label using independent evidence (industry match, footnote text, borrower name in other filings, public credit agreement exhibit if any) plus attributes — never attributes alone. Principal size proximity is dropped as evidence (BDCs legitimately hold different slices of the same syndicated loan, so it's noise, not signal). A MATCH requires at least one independent signal in addition to name/maturity/spread; otherwise label UNSURE (§12.2).
Use UNSURE freely. Report precision/recall twice — once treating UNSURE as NO_MATCH, once as MATCH — plus the raw UNSURE count, in /api/metrics and the README (§12.3). Don't report only the excluded-UNSURE version.
Headline precision is AUTO-only, with its Wilson interval. The second figure is the REVIEW band's own precision from blind held-out labels. Review-queue confirmations never enter any metric (§12.6).
200 hand-labeled pairs, in two phases: 100 tuning pairs first, matcher frozen, then 100 held-out pairs stratified by the now-frozen score bands (§12.6) — not stratified before tuning, which would misalign bands against whatever thresholds tuning picks.
DECISIONS.md including the (non-circular) labeling approach and the score-band stratification.
Schema-drift fixture test per filer.
10.3 Stretch (buffer time only)
Splink benchmark, same input features as rapidfuzz — fair comparison. State in the README whether built.

11. Edge Cases to Handle
Case
Example
Required behavior
Legal-suffix variants
"Acme Holdings, LLC" vs "ACME HOLDCO INC"
Normalize suffixes
Numbers in names (do NOT strip)
"Acme Holdings 2, LLC" vs "Acme Holdings, LLC"
Different entity — never strip digits
Multiple concurrent facilities
Term loan + revolver + delayed-draw, same borrower
Never collapse to one match on name alone
Instrument type must match exactly
First lien vs second lien, same maturity
NO_MATCH
Maturity drift
3/31/2028 vs 6/30/2028
Match within window (§12), not exact equality
PIK component
"S+525 Cash plus 2.50% PIK"
Compare total spread (cash + PIK)
Mismatched period-end
12/31 vs 9/30
Excluded before matching entirely
Equity/unfunded commitments
Common equity, undrawn revolver
Excluded from MVP
Null or zero principal
principal = 0 or NULL
fair_value_pct_par = NULL, row excluded from comparisons, never divide by zero
Non-USD principal
Corpuls, principal in EUR, fair value in USD
fair_value_pct_par = NULL, row kept with excluded_reason NON_USD_PRINCIPAL, never converted
Unfunded loan commitment
HPS row whose footnote says the position or portion is an unfunded loan commitment, with negative or partial cost and fair value
fair_value_pct_par = NULL, row kept with excluded_reason UNFUNDED_COMMITMENT, detected by footnote text
Partly unfunded footnote, normal ratio
ORCIC row, footnote 'partially unfunded debt or equity commitment', fair value about 0.986 of principal
Not excluded: the filer's pattern does not match; fair_value_pct_par is computed
Filer-specific XBRL tags
Non-standard tag names
One schema-drift fixture per filer
Second quarter ingested
Facilities from two period ends
Separate rows with period labels; no cross-quarter link, no metric coverage
Cluster with fewer than 2 usable marks
2-holding cluster, one has zero principal
Not materialized as a facility; compare.py logs it
Same real borrower, names normalize differently
"Acme Holdings" vs "Acme Holdco"
Two borrowers. Unmeasured step, stated in limitations


12. Labeling — Non-Circular Design (read before labeling a single pair)
12.1 Why the naive rubric was circular
Defining "same facility" by name-score ≥ threshold + same type + maturity window + spread window — the same features and thresholds the matcher uses — means the matcher will trivially reproduce the label. Precision/recall measured this way would look excellent for the wrong reason: you'd be checking whether the matcher agrees with its own rule, not whether it identifies real matches.
12.2 The fix: label on independent evidence, plus attributes — never attributes alone
When labeling a candidate pair, use signals the matcher does not consume:
Industry field agreement (carried in normalized_holdings.industry)
Footnote text (footnotes_raw/footnotes) — footnotes often disclose co-lenders or cross-references
Borrower name as it appears in other filings (cross-reference, not the two names being compared)
Public credit agreement exhibit, if one is filed for the borrower — the strongest signal when available, since it may directly name co-lenders
Limitation to state in DECISIONS.md and the README: the cross-filing names the labeling page shows (E11 crossFilingNames) are matched by exact equality of normalized names, using the matcher's own normalizer. That evidence is independent of scores and bands, but not of normalization. A borrower the normalizer spells differently in two filings will not show up there.
Dropped as evidence: principal size proximity. Different BDCs legitimately hold different slices of a syndicated loan (this document says so elsewhere), so similar or different principal amounts tell you nothing about identity — it isn't independent, it's just noisy.
Maturity and spread are your strongest real evidence — don't ban them, but don't label from them alone. Rule: a MATCH label requires at least one independent signal above (industry, footnote, cross-filing name, or credit agreement) in addition to whatever the attributes (name, maturity, spread) suggest. If no independent signal is available or decisive, label UNSURE rather than relying on attributes alone. This is the actual fix for circularity — not refusing to look at maturity/spread, which would make almost everything UNSURE.
12.3 Use UNSURE freely — and report both bounds
If the rule in §12.2 isn't satisfied, label the pair UNSURE. Don't force MATCH/NO_MATCH to hit a target.
Excluding UNSURE pairs biases the metrics toward easy cases. Report precision/recall twice: once treating UNSURE as NO_MATCH, once treating UNSURE as MATCH. The gap between the two is an honest range, not a single cherry-picked number. Report the raw UNSURE count alongside both. This applies to every label-derived number in the metrics.
12.4 Thresholds — made internally consistent
Fuzzy-name floor and the REVIEW band's lower edge are the same number: 0.80 (previously inconsistent at 0.80 vs 0.75). Rationale to write in DECISIONS.md: below 0.80, a pair is unlikely to be worth even a human review glance, so there's no reason for a separate, lower "maybe" floor.
Bands: score ≥ 0.92 → AUTO; 0.80 ≤ score < 0.92 → REVIEW; score < 0.80 → NO_MATCH.
Maturity window (default 3 months) and spread window (default 50 bps) remain tunable defaults for blocking/candidate generation, adjustable once Day 1 shows real amendment-drift patterns — they are not the labeling rule (§12.2).
12.5 Recall limit — state this, don't hide it
Your labeled sample is drawn from blocked candidates — pairs the blocking step already decided to compare. Therefore the precision/recall from that labeled set is recall given blocking, not recall over all possible true matches. Add one explicit README line saying this.
Measuring blocking recall itself requires an independent check, not a check on your blocked-sample labels. Every pair in your labeled set shares a block by construction, so "did my labeled MATCHes share a block" can never fail — it's circular in exactly the way §12.1 describes, just one level removed. Correct method: pick ~30 holdings at random, independent of blocking, manually find their true counterparts in the other BDCs' schedules (by eye, by borrower name — outside the pipeline entirely), and check whether blocking would have paired each found pair into the same block_key. Report this rate as the actual blocking-recall measurement.
12.6 Sampling discipline — two-phase labeling, because bands depend on frozen thresholds
Score bands are defined by the thresholds, and thresholds get tuned from labeled data — so stratifying the held-out set by band only makes sense after the matcher is frozen. Labeling all 200 pairs before tuning, then stratifying, would mean a tuning-driven threshold move silently misaligns the held-out bands from what actually ships. Fix: label in two phases, matcher frozen in between.
Days 6–7: label 100 tuning pairs (blocked sampling, no stratification needed yet — bands don't exist until thresholds are set).
Day 8 morning: tune thresholds on the 100 tuning pairs. Then freeze the matcher — normalization, blocking, scoring, and band edges all lock. The freeze is a recorded step: python -m pipeline.config --freeze stores the matcher hash in matcher_freeze, and from then on normalize.py, block.py and match.py refuse to run. No further changes.
Day 8 afternoon: draw and label the held-out 100, sampled randomly within each now-frozen band (e.g. AUTO ≥0.92, REVIEW 0.80–0.92, just-below 0.65–0.80, low <0.65; ~25/band). Record each band's frame size (measured-period candidate pairs minus the tuning pairs, into band_sizes.band_size), needed to weight precision/recall across bands.
Any matcher change after step 3 invalidates the held-out set. If a bug forces a change, re-draw and re-label a fresh held-out 100 against the new frozen bands — don't reuse the old one.
Pool and enforcement. Tuning and held-out pairs are drawn only from candidate pairs in the measured period, and the held-out frame excludes the tuning pairs. The sampling script assigns each held-out pair its band from candidate_pairs.score at draw time and stores it in label_samples.score_band. Freeze enforcement (full rules in phase_wise.md §6.8): config --freeze writes the matcher hash (the config sections plus the matcher source files) to matcher_freeze. The held-out draw refuses to run without a freeze row, refuses if the current hash differs from it, and copies the hash into band_sizes. evaluate.py refuses if the current hash differs from either. This enforces step 4 mechanically, including the window between the freeze and the draw. Metrics read only labeled_pairs, label_samples, band_sizes and blocking_recall_checks. They never read candidate_pairs.status, so review-queue clicks cannot reach any number.
What is reported (all from blind held-out labels, each with its UNSURE range per §12.3):
Headline: AUTO-only precision, Wilson interval on the AUTO band sample. This is what ships with zero human review.
REVIEW band precision, Wilson interval on the REVIEW band sample. This shows how much work the review queue has to do.
Optional: precision if REVIEW pairs were auto-accepted, band-weighted over AUTO and REVIEW, bootstrap interval. Label it exactly that. It is the only combined figure that stays non-circular.
Recall given blocking, for AUTO-only and (optional) if REVIEW pairs were auto-accepted, band-weighted over all four bands, bootstrap interval.
Blocking recall from the independent 30-holding check (§12.5), Wilson interval on the hand-found pairs.
Weighting: let m_b be the matched share of band b's sample (UNSURE counted per §12.3) and N_b the band's frame size from band_sizes (step 3), so the estimates describe the frame, which excludes the tuning pairs. For a predicted-positive set S of bands, precision is sum(m_b * N_b for b in S) / sum(N_b for b in S) and recall is sum(m_b * N_b for b in S) / sum(m_b * N_b for all bands). Recall leans on the JUST_BELOW and LOW samples scaled up by band size, so expect a wide interval and report it as is. Wilson intervals (95%) are used where a figure is a single-band proportion (items 1, 2, 5). Weighted figures are not simple proportions, so their interval comes from bootstrap resampling over bands: resample each band's labeled pairs with replacement, recompute, repeat about 1000 times, take the 2.5th and 97.5th percentiles.
Not reported anywhere: any precision that includes human review-queue confirmations. A confirmation is a UI click made with the score visible, not ground truth (test 15). README and resume claims use item 1 plus item 2.
Write in DECISIONS.md: the two-phase design and why, the frozen band definitions, per-band sample sizes, the freeze mechanism and what the matcher hash covers, the crossFilingNames normalizer limitation (§12.2), and why no review-confirmed figure is reported.
12.7 The labeling page must hide the matcher's score and status
When building the Day 6 labeling page, do not display the candidate's match score, AUTO/REVIEW/NO_MATCH status, or score band while labeling, and serve samples in the stored random draw_order so the ordering leaks nothing either. Seeing the score anchors your judgment toward agreeing with the matcher, which reintroduces circularity through the UI rather than the rubric. Show only the raw attributes and the independent-evidence fields (industry, footnotes, cross-filing names) — pull the score back in only afterward, when computing metrics.
12.8 Divergence classification
Divergence per facility is max(fair_value_pct_par) - min(fair_value_pct_par) over its included holdings, in points of par (3.2 means 3.2 points). Use NUMERIC in SQL and Decimal in Python, never floats, so the boundaries below are exact.
under 1.0 → AGREEMENT
1.0 up to but not including 2.0 → MILD
2.0 or more → FLAGGED
Cutoffs live in config.yaml as divergence.mild_pts: 1.0 and divergence.flagged_pts: 2.0. compare.py applies them and writes the flag into facility_summary; the API never reads config. Use FLAGGED everywhere (schema, API, UI, tests). Exactly 1.0 is MILD and exactly 2.0 is FLAGGED.
Sensitivity table: for each threshold t in {1, 2, 5}, flaggedCount(t) is the number of facilities with divergence_pts >= t. The API computes it live from facility_summary, so it reflects the final compare.py run on the frozen matcher. It is not part of the held-out evaluation.
12.9 Blocking efficiency and run times (report only)
Blocking exists so the pipeline does not compare every pair. These figures show that the mechanism works. They are measured, never estimated, and they are report-only.
all_pairs: the number of cross-BDC, same-period holding pairs among normalized_holdings of the measured period (all instrument types). Compute it from per-BDC counts, summing n_i * n_j over BDC pairs, not by enumerating pairs.
candidate_pairs: rows in candidate_pairs for the measured period, all statuses.
candidate_share = candidate_pairs / all_pairs and pairs_avoided_pct = 100 * (1 - candidate_share).
Run times: wall-clock seconds for block.py, match.py and compare.py on the measured quarter, median of 3 runs, taken under the frozen matcher config, with the machine (CPU, RAM, OS) written beside them.
Rules:
Pairs avoided is never quoted without blocking recall (§12.5). A blocker that avoids 99.9% of pairs and misses true matches is a bad blocker.
Report-only: the numbers go to docs/data_report.md and the README. Never to the API, never to metric_results, never a tuning target.
Never retune blocking after the Day 8 freeze to improve them. A blocking change invalidates the held-out set (§12.6).
The data is small (3 BDCs, one quarter). These numbers show the mechanism, not scale. Say so.
A resume bracket for them ([R], [B]) stays empty until measured.

13. Test Cases to Pass
#
Test
Input
Expected
1
Normalization — suffix variants
"Acme Holdings, LLC", "ACME HOLDCO INC"
Normalize to comparable form
2
Normalization — don't strip digits
"Acme Holdings 2, LLC"
Digit retained
3
Matching — true match
Same borrower, type, maturity 2mo apart, spread 20bps apart
candidate_pairs.status reflects band correctly given score
4
Matching — instrument type mismatch
First lien vs second lien, same maturity
NO_MATCH regardless of name score
5
Matching — band boundary
score exactly 0.80
REVIEW, not NO_MATCH (inclusive lower bound)
6
Idempotency
Ingest same accession_number twice
Row counts unchanged
7
Schema drift
One fixture per filer format
Correct normalized_holdings row for each
8
Divergence — agreement
diff = 0.5pt
AGREEMENT
9
Divergence — flagged
diff = 3.0pt
FLAGGED
10
Period-end filter
12/31 vs 9/30
Pair excluded pre-matching
11
Null/zero principal guard
principal = 0
fair_value_pct_par = NULL; row kept in facility_comparisons with excluded_reason, not used in divergence or lender_count; principal in EUR with fair value in USD gives NULL with excluded_reason NON_USD_PRINCIPAL; a row whose footnote marks an unfunded loan commitment gives NULL with excluded_reason UNFUNDED_COMMITMENT; an ORCIC row with a 'partially unfunded' footnote and a normal ratio keeps its computed value
12
API — endpoint shape
GET /api/facilities/:id/comparison
Matches CONTRACT.md E5, sourceUrl present
13
API — review actions
E7 confirm, E8 reject, in either id order
Confirm on REVIEW → CONFIRMED; confirm on any other status → 409; reject accepts AUTO, REVIEW, CONFIRMED; reject on NO_MATCH or REJECTED → 409
14
Facility-building excludes REVIEW/REJECTED
A pair with status=REVIEW
Not included in holding_facility_map clustering
15
labeled_pairs/candidate_pairs separation
A UI-confirmed pair
Does NOT appear in labeled_pairs unless independently labeled
16
REJECTED as cannot-link
A–C AUTO, B–C AUTO, A–B REJECTED
A and B never share a facility. The lower-scoring of the two AUTO edges is skipped (ties by ascending ids) and compare.py logs the skip
17
Same-BDC collision routed to review
Clustering would otherwise place two holdings from the same BDC in one cluster
Whole cluster routed to review queue, not turned into a facility
18
Borrower grouping
"acme holdings 2" and "acme holdings" facilities in one period; one borrower with a single facility
Exact equality only: the two names are separate borrowers; the single-facility borrower exists
19
Cluster naming determinism
Cluster with two names tied on frequency; compare.py run twice
Alphabetically first name wins; both runs produce identical names and groupings
20
Facility materialization
2-holding cluster where one holding has zero principal; 3-holding cluster with one zero
First is not a facility; second is, with excluded_count = 1 and lender_count = 2; CHECK (lender_count >= 2) holds
21
Divergence boundaries
diffs 0.99, 1.0, 1.99, 2.0 as Decimal
AGREEMENT, MILD, MILD, FLAGGED
22
E5 contract
Any facility
Body has fixed periodEnd, no availablePeriods, sourceUrl on every row; a fixture facility with fewer than 2 rows returns 500 DATA_INTEGRITY
23
E9 nulls and no review leakage
Before evaluate.py runs; then flip candidate_pairs.status of held-out pairs
Every label-derived field is null and there is no measured field; flipping statuses leaves the label-derived payload unchanged
24
Labeling endpoints
E11 and E12 with the flag off and on
Off: 404. On: E11 never returns score, status, band, phase or draw order; E12 writes only labeled_pairs and derives sampling_method and score_band from label_samples
25
Freeze enforcement
(a) held-out draw with no freeze row; (b) edit a hashed config key or source file after --freeze, then run the held-out draw; (c) edit after the draw, then run evaluate.py; (d) run normalize.py, block.py or match.py while frozen; (e) --unfreeze
(a), (b), (c) and (d) are refused with a clear message. (e) removes the freeze row and every held-out artifact, including metric_results, and leaves tuning samples and labels
26
Second quarter
Ingest a non-measured quarter
Its facilities show their own periodEnd; no pair from it appears in label_samples


14. Scaling Plan (ideation only, not built)
Full ~40–50 public BDC coverage; full historical quarter depth; incremental/near-real-time ingestion on new filing detection; cross-period facility linking (following a facility across quarters), which is a new unmeasured step and needs its own labeled evaluation; stable IDs across rebuilds; partitioning blocking, scoring and comparison work by block key across workers, since blocks are independent. The README's "If this ran at scale" section is built from this list and is marked as ideation, not built.

15. Design Decisions You Must Be Able to Defend
Forced: staged matching pipeline; facility-level, %-of-par comparison (null/zero-guarded); raw/staged/curated layering; source URL + review queue; same-period-end hard filter.
Arbitrary — needs a measured defense:
The matcher → held-out precision/recall (reported as a MATCH/NO_MATCH range across UNSURE treatment, §12.3), measured against independent evidence plus attributes, never attributes alone (§12.2) — this is the single most important defense in the whole project.
Match-confidence bands (unified at 0.80/0.92) → written rationale in DECISIONS.md (§12.4).
Divergence threshold → the 1/2/5pt sensitivity table.
Blocking windows (3mo maturity, 50bps spread) → defaults, tunable from Day 1 data, used for candidate generation only, never for labeling.
Two-language stack → "Python for linkage tooling, Node for my strongest language and the JD's stack."
Structured-XBRL-first, HTML-fallback → verified Day 1.
Keeping labeled_pairs separate from candidate_pairs/UI confirmations → a user confirming a match in the UI is not the same epistemic act as a labeler checking independent evidence; conflating them would quietly reintroduce circularity through the back door.
One measured quarter, no period selector → a facility belongs to one period by construction, and linking facilities across periods would be a new unmeasured step, so the MVP makes no cross-quarter claim.
Borrower grouping by exact normalized-name equality → deliberately simple and deliberately unmeasured: say so in the limitations and never count it toward matcher precision.
Precision reporting: AUTO-only headline plus the REVIEW band's own precision, no review-confirmed figure → a confirmation is a UI click made with the score visible, so including it would make the number circular.
Blocking efficiency is report-only → pairs avoided is always shown next to blocking recall, never alone, and never used to retune blocking after the freeze (§12.9).
The freeze is a recorded step, not a convention → config --freeze stores a hash of the matcher (the config sections plus the matcher source files) in matcher_freeze. The matcher scripts refuse to run while it exists, and the held-out draw and evaluate.py refuse if the hash has changed, so an edit between the freeze and the draw cannot slip through.

16. How to Present on Your Resume
16.1 Bullet variants (pick one per application, never merge them)
Fill every bracket from a measured value. A bullet with an empty bracket is not ready to send.
A. Asset managers, banks, fund services and fintech vendors (for Apollo only, add "including Apollo Debt Solutions BDC" after "portfolios"): "Built a pipeline resolving borrower and facility identity across 3 SEC-filed BDC portfolios and comparing fair-value marks at the facility level (% of par), with a review queue for uncertain matches, a tolerance flag for valuation divergence, and a source filing link on every figure. AUTO-only precision [X]% (95% CI [a, b]) on a blind, band-stratified held-out set from one measured quarter. Python, Node/Express, PostgreSQL, React, Docker, GitHub Actions."
B. Big 4, Accenture, Capgemini and consulting tech arms: "Delivered a full-stack data product (Python, Node/Express, PostgreSQL, React, Docker, GitHub Actions) that traces every displayed number to a public SEC filing, with documented methodology, a review workflow for uncertain matches, and a measured evaluation on a blind held-out set."
C. Big tech and SDE roles: "Built an idempotent entity-resolution pipeline with blocking (pairs avoided [R]%, blocking recall [B]%), deterministic output, indexed PostgreSQL storage, [N] automated tests in CI, and a blind held-out evaluation with confidence intervals."
16.2 Rules for Resume Numbers
State only numbers actually measured on the held-out set, labeled with independent evidence.
Quote AUTO-only precision plus the REVIEW band's precision, and never a figure that includes review-queue confirmations. Say "recall given blocking" and give blocking recall separately.
[R] (pairs avoided) and [B] (blocking recall) come from the frozen matcher and are quoted together (§12.9). Run times are never quoted without the machine they ran on.
[N] is the test count from the CI run, not the number of rows in the §13 table.
Never imply Splink results if not built. Never state market-wide coverage. Never claim Java or Spring Boot experience this project does not contain.
The ICE anchor-partner sentence belongs to the Apollo pitch and cover letter only. It is not part of variants B or C.
16.3 Other Places to Show It
GitHub README (evaluation section first); demo video and screenshots; for Apollo only, a cover-letter mention tied to the ICE anchor-partner fact, framed as independently verified.

17. Company-Specific Tailoring
The company list and the notes on it come from you. The table is my reading of how each segment screens, not verified hiring data. Check each JD and each team's own vocabulary before tailoring.
17.1 Fit by segment
Segment
Companies
What they likely screen on
Lead with
Don't
Asset managers
Apollo, Fidelity, Vanguard, Invesco
Data engineering, reconciliation or valuation familiarity
The valuation transparency gap. For Apollo only: the ICE anchor-partner link and Apollo's own filing as source data
Claim knowledge of internal systems
Fund services and fintech vendors
State Street, Northern Trust, SS&C, Broadridge, FIS, Fiserv, Temenos, Finastra, Charles River
Fund and portfolio data, reference data, controls, reliability
Comparing the value of the same asset across funds with a tolerance flag, a review queue for uncertain matches, and a source on every number
Describe how their pricing process works. Ask.
Banks
UBS, Wells Fargo, HSBC, Standard Chartered, Nomura, BNP Paribas, Credit Agricole
Reference data, reconciliation, valuation control, audit trail
Entity resolution across noisy sources, measured evaluation, the evidence trail
Call it independent price verification. It resembles it.
Big 4, Accenture, Capgemini
EY, Deloitte, PwC, KPMG, Accenture, Capgemini
Communication and aptitude first, then delivery
Provenance and reproducibility, full-stack delivery with tests and CI. For EY, Deloitte, PwC and KPMG, frame it as data engineering for financial services clients
Lead with finance jargon
Strategy and analytics consulting
McKinsey (QuantumBlack), BCG X
Problem solving and analytical rigor
The evaluation design: blind labels, stratified held-out sampling, intervals, avoiding circularity
Overclaim impact
Big tech
Any
DSA and system design far more than projects
The engineering: blocking, idempotency, determinism, indexes, tests
Claim scale. The data is small.

Your notes, unverified: State Street, Northern Trust, SS&C and Broadridge deal with fund and portfolio data all day, so the project is especially relevant there. Consulting firms hire in big batches and screen on aptitude and communication more than projects, so practice the 2-minute explanation (§19.2).
17.2 Vocabulary swap
Rule: never call two different things "exception" in the same answer. A valuation divergence is a tolerance exception. The review queue is for uncertain matches.
In this project
Banks and fund services
Big 4 and consulting
Big tech
Divergence flag
Tolerance exception
Variance flag
Threshold alert
Review queue (uncertain matches)
Match review queue
Reviewer sign-off on uncertain matches
Human-in-the-loop queue
source_url on every row
Evidence trail
Audit evidence
Data lineage
Held-out labeled set
Blind sample testing
Sample testing
Offline evaluation

17.3 Honest limits
Consulting screening is mostly aptitude and communication, per your note. The project helps but will not decide it.
For big tech, the project can help with resume screening. DSA preparation decides most of the rest, so do not trade DSA time for polish.
This plan has no Java or Spring Boot. For any JD that lists Java, say plainly that you built in Python and Node and can pick Java up.
Fund services and bank framing is my reading of the shape of their controls. Check the vocabulary against each team's own JD.

18. Weekly Plan — day-level detail
Day
Tasks
Hard gate / stop point
1
§4.6 checklist: XBRL parse → CIK confirm → User-Agent header → pick 2 more BDCs → version check
XBRL parsing must succeed
2
Vertical slice: 1 filing → raw layer → API → bare React table, in Docker Compose
Gate: if XBRL parsing is still broken, shrink scope now
3
Full schema (§6: raw, staged, curated and evaluation tables, incl. candidate_pairs), idempotency test, CI skeleton. CONTRACT.md is frozen from here: change it only with a note in DECISIONS.md


4
Ingest all 3 BDCs, schema-drift fixtures per filer
Allowed to slip into Day 5
5
Normalize, block, exact-match baseline, rapidfuzz scorer → populate candidate_pairs; print all pairs versus candidate pairs (informational, §12.9)


6 (AM)
Labeling endpoints (E11, E12 behind ENABLE_LABELING), sample_labels.py --phase tuning, and the labeling page: shows independent evidence, hides score, status, band and phase (§12.7); Match/No/Unsure keys


6 (PM)
Phase 1: label the 100 tuning pairs (~1.5h). Then start provisional compare.py (AUTO pairs only: clustering rules, facility materialization, borrower grouping, divergence)
You label — never delegate. A MATCH needs an independent signal, not attributes alone
7
Finish provisional compare.py and its tests (18 to 21); build E1 to E8 and E10 from CONTRACT.md; Claude Code starts the core four screens against the real endpoints
Real facilities visible in the browser, even if provisional
8 (AM)
Tune thresholds on the 100 tuning pairs, then freeze the matcher (normalization, blocking, scoring, band edges) and store the matcher hash with python -m pipeline.config --freeze. Just before freezing, run block.py and match.py 3 times so their timings are logged under the frozen config (§12.9)
Freeze point — do not revisit after Phase 2 labeling starts
8 (PM)
Phase 2: sample_labels.py --phase heldout (stratified by the frozen bands, ~25/band, writes band_sizes); label the held-out 100 (~1.5h); evaluate.py writes metric_results


9
Re-run compare.py on the frozen matcher (final, 3 runs so its timing is logged); build E9 (live sensitivity table and coverage); UI: Comparison, Review Queue (pairs and clusters), Metrics; 30-holding blocking-recall check (§12.5) if time allows


10
Remaining UI (Overview, Facilities, Filings), shape tests for E1 to E12, optional landing page only if everything else is done
First cut if behind: Overview, Facilities, Filings, landing
11
README (checklist §20.3, including the glossary, the "If this ran at scale" section and the data report), finish DECISIONS.md


12
Buffer: absorbs Day 4/5 slippage first; 30-holding blocking-recall check if not done Day 9; Splink only if still on schedule
Only one buffer day now


19. Interview Pitch and Q&A
19.1 30-Second Pitch
Change only the opening sentence per segment. Everything after it is the same: "It resolves the same borrower across different lenders' SEC filings and flags, with measured precision, where their valuations of the same loan diverge."
Segment
Opening sentence
Apollo
"I built a small version of the identifier gap ICE is addressing, with Apollo as its anchor partner."
Other asset managers
"I built a pipeline that resolves the same borrower across different funds' SEC filings and compares how each fund values it."
Banks and fund services
"I compared the valuations of the same asset across funds and flagged tolerance exceptions."
Consulting and big tech
"I built a data pipeline that matches records across noisy sources and measures how well it does."

19.2 2-Minute Version
Five beats. About 20 seconds on each of the first four and 15 on the last, so it lands under 2 minutes if you hold the clock:
The problem: the same loan appears under different names in different funds' filings, and each fund reports its own value.
The approach: normalize, block so you do not compare every pair, score, and send uncertain pairs to a review queue.
The evidence: blind labels using evidence the matcher does not see, a held-out set, and intervals, not a bare accuracy figure.
The result and its limits: AUTO-only precision plus the REVIEW band's precision, 3 BDCs, one quarter.
What you would do next: cross-quarter linking, as its own measured step.
Practice it out loud with a timer. Consulting screens weigh this more than the repo.
19.3 Pitching to a Specific Team
Data engineering: lead with ingestion, schema drift and idempotency.
Reconciliations: lead with matching, the review queue and the tolerance flag.
Valuation, pricing control or fund data (banks, fund services): lead with the tolerance exception, the evidence trail and the blind evaluation.
Consulting delivery: lead with the problem framing, the methodology in DECISIONS.md and what the numbers do and do not show.
Big tech: lead with blocking, determinism, indexes, tests and CI.
19.4 Likely Questions, with answer sketches
"Why not an exact key?" No shared identifier exists across BDC filers.
"How do you know your matcher works?" Held-out precision/recall, sampled within each score band so the bands aren't starved — and critically, a MATCH label required at least one piece of evidence the matcher itself doesn't see (industry, footnotes, cross-filing names), not attributes alone, so the evaluation isn't just checking whether the matcher agrees with its own rule.
"What does your recall number actually mean?" It's recall given blocking. I measured blocking's own recall separately and independently — picking ~30 holdings at random, manually finding their true counterparts across the other BDCs' schedules, and checking whether blocking would have paired them — since checking my already-blocked labeled sample for this would be circular (every labeled pair shares a block by construction).
"Why facility-level, not borrower-level?" Different tranches carry different risk; raw-dollar or borrower-level comparison manufactures false disagreement.
"How did you choose the divergence threshold?" A sensitivity table across 1/2/5 points of par.
"Is your API read-only?" Read-mostly. Review-queue confirm and reject update candidate_pairs only. A separate labeling endpoint writes labeled_pairs, but it is mounted only when ENABLE_LABELING=true (off by default, since there is no auth). Queue clicks never reach the labeled ground truth or any metric.
"What's the weakest part?" One person labeled the data, UNSURE pairs are reported as a range instead of dropped, borrower grouping is exact name equality and unmeasured, and the measured set is 3 BDCs in one quarter.
"What precision do you report?" AUTO-only precision with a Wilson interval, plus the REVIEW band's own precision, both from blind held-out labels. I do not report a figure that includes review-queue confirmations, because those are clicks made with the score visible, not ground truth.
"Do you claim anything across quarters?" No. A facility belongs to one quarter by construction, and linking across quarters would be a new step that needs its own labeled evaluation.
"How do you avoid comparing every pair?" Blocking. I measured how many pairs it avoids on the measured quarter and, next to it, how many true matches it still finds (blocking recall). The first number alone proves nothing, because a blocker that discards everything also avoids every pair. The data is small, so this shows the mechanism, not scale.
"Why no Java?" The JD lists Java and Spring Boot first. I built this in Python and Node because linkage tooling is Python-first and Node is where I am strongest. The structure carries over: layers, transactions, idempotency, tests, CI. I can pick Java up.
"Explain it to someone outside finance." Use the five glossary lines from the README: a BDC is a public fund that lends to private companies, a syndicated loan is one loan shared by several lenders, fair value is the fund's own estimate of what the loan is worth, par is the loan's face amount, and a mark is that estimate as reported.
19.5 Whiteboard Exercises to Practice
Design the staged matching pipeline. Explain blocking, why all-pairs comparison is quadratic, and how to measure blocking's own recall. Design idempotent ingestion. Explain why labeling on the matcher's own features is circular and how to avoid it. Walk through moving the confidence threshold and its effect on precision/recall.

20. Scope Control, Repository Structure, and README
20.1 Common Mistakes to Avoid
Expanding coverage before the matcher is measured. Polishing UI before the matcher is frozen on Day 8 (building the core screens against real endpoints from Day 7 is fine). Letting an AI agent pre-label data. Claiming Splink results if not built. Comparing raw dollars across tranches. Overloading Day 5. Labeling using the matcher's own features (circularity). Treating UI confirmations as ground truth.
20.2 Repository Structure
/pipeline
  /ingest.py
  /normalize.py
  /block.py
  /match.py             — populates candidate_pairs
  /compare.py           — full deterministic rebuild of curated tables, one transaction
  /sample_labels.py     — draws tuning and held-out samples (refuses the held-out draw unless the matcher is frozen)
  /evaluate.py          — Wilson and bootstrap, writes metric_results (refuses if the config hash changed)
  /blocking_recall.py   — records the independent 30-holding check
  /report.py            — read-only: writes docs/data_report.md (ingest counts, blocking efficiency, run times)
  /config.py            — loads config.yaml and env, computes the matcher hash, `--hash`, `--freeze`, `--unfreeze`
  /config.yaml
/api                     — Node/Express, TypeScript, read-mostly (contract in CONTRACT.md; E11 and E12 behind ENABLE_LABELING)
/web
/tests
  /test_normalize.py
  /test_match.py
  /test_idempotency.py
  /test_schema_drift.py
  /test_api.py
  /test_guards.py        — null/zero principal, etc.
  /test_compare.py       — clustering, borrower grouping, materialization, divergence
  /test_evaluate.py      — null handling, hash refusal, no review leakage
/fixtures
/docs                    — data_report.md, day1_notes.md (run_times.jsonl is appended by block, match and compare)
docker-compose.yml
SPEC.md
CONTRACT.md
DECISIONS.md
README.md

20.3 README Checklist
[ ] Problem statement + verified ICE/Apollo anchor-partner context + retroactive-vs-origination distinction
[ ] Architecture diagram + schema summary + API contract (link CONTRACT.md)
[ ] Write surface stated: E7/E8 write candidate_pairs.status, E12 writes labeled_pairs behind ENABLE_LABELING (default false)
[ ] Evaluation: AUTO-only precision (headline) and REVIEW band precision, each with its Wilson interval and its UNSURE range (UNSURE as NO_MATCH and as MATCH); optional precision if REVIEW pairs were auto-accepted, labeled exactly that, with a bootstrap interval; recall given blocking (bootstrap) and blocking recall from the independent 30-holding check (Wilson); held-out methodology (two-phase: tune on 100, freeze matcher and record the config hash, then band-stratified-sample the held-out 100 from the measured quarter, §12.6); labeled using independent evidence + attributes, never attributes alone; raw UNSURE count; who labeled; one line stating no figure includes review-queue confirmations
[ ] Methodology: link to DECISIONS.md (labeling approach §12, freeze rule, thresholds). No separate methodology page.
[ ] Divergence sensitivity table (1/2/5pt)
[ ] Five-line glossary for non-finance readers: BDC, syndicated loan, fair value, par, mark
[ ] "If this ran at scale": partition blocking, scoring and comparison by block key across workers, incremental ingestion on new filings, stable IDs across rebuilds, cross-period linking as its own measured step (§14). Marked as ideation, not built.
[ ] Data report (docs/data_report.md): rows parsed per filing; blocking efficiency (all_pairs, candidate_pairs, pairs avoided %) shown next to blocking recall; run times of block.py, match.py and compare.py with the machine spec (§12.9). Report only, never retuned.
[ ] Honest note on Splink (built or skipped)
[ ] Known limitations: 3 BDCs in one measured quarter (a second quarter is unmeasured and unlinked), one-person labeling, tranche/seniority caveats, blocking-recall caveat, borrower grouping is exact normalized-name equality and unmeasured (never part of matcher precision), IDs regenerate on every compare.py run, same-BDC collision clusters need manual resolution, labeling evidence from other filings uses the matcher's own normalizer (independent of scores and bands, not of normalization)
[ ] Source filing URL convention
[ ] How to run: docker compose up

Spec is locked. Begin Day 1 now.

