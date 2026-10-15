phase_wise.md: Backend + AI plan
Project: Cross-Lender Private Credit Valuation Monitor. Scope, schema, evaluation method and tests come from SPEC.md. Endpoint shapes come from CONTRACT.md. This file covers backend and AI/matching only. "AI" here means deterministic entity resolution (normalization, blocking, rapidfuzz scoring, measured evaluation). There is no LLM anywhere in the pipeline. The UI plan is frontend.md, and section 2 below is identical in both files.
1. Rules
3 BDCs: Apollo Debt Solutions BDC (CIK 1837532) plus 2 chosen by real overlap. One measured quarter (MEASURED_PERIOD_END in .env). Same period end only. A second quarter may be ingested but is unmeasured and unlinked.
The pipeline is a standalone Python 3.11 CLI (python -m pipeline.<module>), never imported by Node. The API is Node 24, Express 5, TypeScript. Postgres 16. Docker Compose v2.
No ORM. Parameterized SQL in Python (psycopg) and Node (pg).
All tunables live in one file, pipeline/config.yaml. Secrets, the SEC contact string and the measured quarter live in env vars.
source_url is carried through every table that holds a holding-level row.
fair_value_pct_par is NULL when principal is NULL, 0 or not in USD. Never divide by zero.
Same-BDC pairs and cross-period pairs are never scored or clustered.
The matcher freezes on Day 8 morning: normalization, blocking, scoring, band edges. After the held-out draw, any matcher change invalidates the held-out set (config --freeze and the matcher hash, section 6.8).
No AI tool pre-labels data. You label every pair, using independent evidence (SPEC section 12.2).
Review-queue clicks never enter any metric. evaluate.py never reads candidate_pairs.status.
Writes through the API: E7 and E8 update candidate_pairs.status. E12 writes labeled_pairs and exists only when ENABLE_LABELING=true.
Non-claims: not Apollo's internal valuation, not ICE ID reverse engineering, not market-wide, no cross-quarter claim.
Blocking efficiency (pairs avoided) and run times are report-only (SPEC section 12.9): measured on the frozen config, quoted only next to blocking recall and the machine spec, never an API field, never a tuning target.
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

Writes: E7 and E8 update candidate_pairs.status. E12 writes labeled_pairs and is mounted only when ENABLE_LABELING=true. Every other endpoint is read-only.
3. Day map
Day
Phase
Backend and AI deliverable
What the UI needs (frontend.md)
1
0 Verify
ADS Inline XBRL parsed, 2 more BDCs and the measured quarter chosen, versions checked
nothing
2
1 Vertical slice
One filing to raw tables to one API route to a bare table
bare table (temporary dev route)
3
2 Schema, CI, freeze
All 18 tables, idempotent ingest, CI, CONTRACT.md frozen
contract frozen
4 (may slip to 5)
3 Full ingest
3 BDCs ingested, schema drift fixtures, data report
nothing
5
4 Matching
normalize, block, score, candidate_pairs
nothing
6 AM
5 Labeling tools
E11, E12, tuning sample draw
label page
6 PM
5 and 6
You label 100 tuning pairs, start provisional compare.py
nothing
7
6 Facilities and API
Provisional compare.py, E1 to E8 and E10
core four screens start
8 AM
7 Tune and freeze
Thresholds from tuning labels, freeze, config hash
nothing
8 PM
7 Held-out
Held-out draw, you label, evaluate.py
label page
9
8 Final build
Final compare.py, E9, 30-holding blocking recall check
Comparison, Review, Metrics
10
9 Hardening
Contract tests for E1 to E12, indexes, CI green
remaining pages
11
10 Docs
DECISIONS.md, README backend sections
nothing
12
11 Buffer
Slippage first, Splink only if everything else is done
nothing

4. Runtime
4.1 config.yaml (all tunables, one place)
# the measured quarter is not set here: MEASURED_PERIOD_END in .env (read by the pipeline and the API)
sec:
  max_requests_per_second: 5       # SEC allows 10, stay well under
  backoff_seconds: [1, 2, 4, 8]    # user agent comes from env SEC_USER_AGENT
normalization:
  legal_form_tokens: [llc, inc, corp, corporation, co, company, lp, llp, ltd, limited, plc]
  structural_tokens: [holdings, holding, holdco, topco, parent, intermediate]
  instrument_keywords:             # checked in this order, first hit wins
    revolver: [revolv]
    delayed_draw: [delayed, ddtl]
    second_lien: [second lien, 2nd lien]
    first_lien: [first lien, 1st lien, senior secured, unitranche]
    unsecured: [unsecured, subordinated, mezzanine]
  equity_keywords: [common stock, preferred, warrant, units, membership interest, partnership interest, equity]
blocking:
  maturity_window_months: 3
  spread_window_bps: 50
  name_prefix_chars: 4
  max_block_size_warn: 200
scoring:
  scorer: token_sort_ratio         # name only, attributes gate candidacy in blocking
bands:
  auto_min: 0.92
  review_min: 0.80                 # inclusive, same number as the fuzzy floor
  just_below_min: 0.65
divergence:
  mild_pts: 1.0
  flagged_pts: 2.0
sampling:
  tuning_size: 100
  heldout_per_band: 25
  seed: 1                          # fixed so draws are reproducible
evaluation:
  bootstrap_resamples: 1000
  bootstrap_seed: 1
  ci_level: 0.95
blocking_recall:
  sample_size: 30
  seed: 1
freeze:
  hashed_files: [pipeline/normalize.py, pipeline/block.py, pipeline/match.py]   # add any helper module they import

All values above are defaults to tune on tuning labels only, before the freeze. The matcher hash covers the normalization, blocking, scoring and bands sections and the contents of the files in freeze.hashed_files (section 6.8). divergence, sampling and evaluation are not part of it.
4.2 Env vars (.env.example)
DATABASE_URL, SEC_USER_AGENT (your name and email, required by SEC), MEASURED_PERIOD_END (ISO date of the measured quarter, set on Day 1, read by both the pipeline and the API), ENABLE_LABELING (default false), PORT. The Node API reads env and the database only. It never reads config.yaml: compare.py has already written the divergence flag into facility_summary.
4.3 Compose services
db: postgres:16 with a healthcheck (pg_isready).
api: Node 24, depends on db healthy, healthcheck on GET /api/overview.
web: built frontend served by nginx or vite preview.
pipeline: Python image under a tools profile. Run jobs with docker compose run --rm pipeline python -m pipeline.compare. It is not a long-running service.
Default compose has ENABLE_LABELING=false. A local override file turns it on while you label.
4.4 CI (GitHub Actions)
Four jobs, all must pass: pipeline tests (pytest with coverage, Postgres service container), API tests (Node 24, Postgres service container), web typecheck and build, Docker image build. Pin Python, Node and Postgres versions identically in Dockerfiles and the workflow. The pipeline job fails on any test failure.
4.5 Migrations
Numbered SQL files in db/migrations/ (001_raw.sql, 002_staged.sql, and so on) applied by a small runner that records them in a schema_migrations table. No ORM. Beyond the SPEC section 6 tables, add these indexes in the migrations: candidate_pairs(status, score DESC), candidate_pairs(holding_id_b), normalized_holdings(period_end_date, bdc_cik), blocking_keys(block_key), facility_comparisons(facility_id), canonical_facilities(canonical_borrower_id), label_samples(phase, draw_order).
5. Phases
Each phase lists tasks, tests (numbers from SPEC section 13), and a gate. If a gate fails, use the stated fallback instead of pushing on.
Phase 0: Verify (Day 1)
Goal: prove the ingestion path before building anything on it.
Set the SEC User-Agent from env. Fetch https://data.sec.gov/submissions/CIK0001837532.json. Confirm the company name and the recent 10-Q list. Confirm no 403s. Add the rate limiter and backoff now.
Pick the latest 10-Q with a Schedule of Investments. Download the primary Inline XBRL document from the filing folder under https://www.sec.gov/Archives/edgar/data/. Save it under fixtures/raw/.
Parse with lxml: read ix:nonFraction facts, resolve each fact's context, and resolve the context's dimension members. Look for facts for fair value, principal, cost, maturity date and interest rate or spread, with each investment identified by a dimension or typed member. Do not assume tag names. Verify them on this filing. Do not use the companyfacts API, it drops dimensional facts.
Count funded rows (nonzero principal) that also have fair value. If at least 95% of funded rows parse from ix facts, ingestion is XBRL-first for this filer. Otherwise parse the HTML schedule tables with pandas as the primary path for this filer. Record the decision per filer.
Scout other BDCs. Shortlist 4 to 5 large public BDCs, confirm each CIK on EDGAR, fetch each one's latest 10-Q, extract rough borrower names, and compute overlap with ADS on a crude normalized-name match. Choose the 2 with the highest overlap that share a quarter-end with ADS. Record that quarter-end as MEASURED_PERIOD_END in .env.
Version check: Node 24 LTS, Express 5, React 19, Postgres 16, Compose v2. Pin Tailwind, the router and any fetching library.
Output: docs/day1_notes.md with CIKs, the quarter-end, overlap counts, the parse decision per filer, and version results.
Gate: ADS parses to at least 50 holdings with principal and fair value, and the 3 BDCs have at least 30 overlapping borrower names in total.
Fallback: if the parse is still broken by the end of Day 2, shrink scope. Use ADS plus the best single overlapping BDC, first lien term loans only, and say so in the README.
Phase 1: Vertical slice (Day 2)
Goal: one filing, end to end, in Compose.
pipeline/ingest.py loads the ADS filing into raw_filings and raw_holdings.
Compose with db, api, web.
The API exposes E10 (/api/filings) plus one temporary route, GET /api/_dev/holdings, mounted only when NODE_ENV=development. It is not part of the contract and is deleted on Day 7.
A bare React table shows the holdings.
Gate: ADS holdings visible in the browser after docker compose up.
Phase 2: Schema, idempotency, CI, contract freeze (Day 3)
All 18 tables from SPEC section 6 as migrations (including the singleton matcher_freeze), plus the indexes in 4.5.
Ingest is one transaction per filing: insert the filing with ON CONFLICT (accession_number) DO NOTHING, and if nothing was inserted, skip the rows entirely. Re-running is a no-op.
The API skeleton has every route in the section 2 index returning 501 until built, the error middleware (error shape and codes from CONTRACT.md), and a contract test harness (supertest).
CI with the four jobs. .env.example committed.
CONTRACT.md is frozen. Change it only with a note in DECISIONS.md.
Tests: 6.
Gate: CI is green on a clean checkout, and docker compose up starts db, api, web.
Phase 3: Full ingest and schema drift (Day 4, may slip to Day 5)
Per-filer adapters (FilerAdapter.parse(filing) -> rows) with tag maps in config. Ingest all 3 BDCs for the measured quarter. A second quarter is optional and is labeled by period only. Each adapter's config also holds its unfunded-commitment footnote pattern (empty for filers where the evidence shows no basis problem), and each filer fixture includes one row with and one without the footnote.
Data report (docs/data_report.md, generated by python -m pipeline.report, which is read-only): per filing, rows total, rows parsed, rows with principal, rows with fair value, rows with footnotes. This feeds the README coverage numbers. After Phase 4 the same report also carries blocking efficiency and run times (section 6.10).
Schema drift fixtures: a trimmed real excerpt (30 rows or fewer) per filer under fixtures/, each with a test asserting the fields normalization needs.
Tests: 7, and a fixture for 26.
Gate: each BDC has at least 50 holdings with principal and fair value, and the report is generated.
Phase 4: AI matching pipeline (Day 5)
normalize.py: section 6.1. Writes normalized_holdings (upsert by holding_id, never truncate).
block.py: section 6.2. Writes blocking_keys and the candidate predicate.
match.py: section 6.3 and 6.4. Writes candidate_pairs, including NO_MATCH rows.
Exact-match baseline: candidates whose normalized names are equal. Report how many pairs the baseline finds versus the scorer.
Print band counts (AUTO, REVIEW, JUST_BELOW, LOW, NO_MATCH). Eyeball 20 AUTO pairs. If more than 3 are obviously wrong, fix normalization or the digit guard before labeling. Pre-freeze tuning by eye is allowed. It is not labeling.
Print blocking efficiency as information: all_pairs (from per-BDC counts, the sum of n_i * n_j), candidate_pairs, and pairs avoided %. These are report-only (SPEC section 12.9). block.py, match.py and compare.py also append their run time to docs/run_times.jsonl automatically (section 6.10).
Tests: 1, 2, 3, 4, 5, 10, 11, plus one unnumbered unit test for the all_pairs formula (section 8).
Gate: candidate_pairs is populated for the measured quarter and the band counts look sane.
Phase 5: Labeling tools and tuning labels (Day 6)
Morning:
sample_labels.py --phase tuning: section 6.6.
E11 and E12 behind ENABLE_LABELING. E11 never returns score, status, band, phase or draw order.
Claude Code builds the label page (frontend.md section 4.9).
Afternoon: 4. You label the 100 tuning pairs (about 1.5 hours). A MATCH needs at least one independent signal (industry, footnote, cross-filing name, credit agreement exhibit) on top of name, maturity and spread. Otherwise UNSURE. Principal size is not evidence. 5. If fewer than 10 of your first 50 labels are MATCH, redraw the remaining tuning pairs with --min-score 0.65. The tuning set only has to be useful for choosing thresholds. Only the held-out set has to be unbiased. 6. Start provisional compare.py.
Tests: 15, 24.
Gate: 100 tuning labels in labeled_pairs with MATCH, NO_MATCH and UNSURE counts noted in your DECISIONS.md draft.
Phase 6: Facilities and API (Day 7)
Finish compare.py (section 6.5). Provisional means it uses AUTO and CONFIRMED pairs at the current thresholds, and it is re-run on Day 9.
Build E1 to E8 and E10 exactly as in CONTRACT.md. Delete the temporary dev route. Contract tests per endpoint: shape, sort order, error codes, null rule.
Informal sanity checks (not reported): spot-check blocking on 10 random holdings, and check 10 displayed comparison rows against the actual SEC filing by hand.
Tests: 8, 9, 11, 12, 13, 14, 16, 17, 18, 19, 20, 21, 22, 26.
Gate: real facilities appear through E4 and E5 in the browser.
Phase 7: Tune, freeze, held-out, evaluate (Day 8)
Morning:
Tune using only the 100 tuning labels: compute precision and recall at candidate auto_min and review_min values (UNSURE shown separately), choose both edges, and review the just_below_min edge. Adjust normalization token lists only on evidence from tuning pairs.
Just before freezing, run block.py and match.py 3 times so their timings are logged under the final config (section 6.10). Then freeze: commit the config and code, run python -m pipeline.config --freeze (it stores the matcher hash in matcher_freeze), and tag git matcher-frozen. From here normalize.py, block.py and match.py refuse to run, and the held-out draw checks the stored hash (section 6.8).
Afternoon: 3. sample_labels.py --phase heldout: section 6.6. It refuses unless the freeze row exists and the current hash matches it, then writes label_samples and band_sizes with that hash. 4. You label the held-out set (about 1.5 hours), same rule as Phase 5. 5. evaluate.py: section 6.7. It writes metric_results.
Tests: 25.
Gate: a matcher_freeze row exists, a metric_results row exists, heldOutCount equals the number of drawn samples, and the three hashes match (freeze row, band_sizes, current).
If a matcher bug turns up after the draw: fix it, --unfreeze (which dumps held-out artifacts, including metric_results, to backups/ and deletes them together with the freeze row), re-freeze, redraw, relabel. Never reuse the old held-out set.
Phase 8: Final build, E9, blocking recall (Day 9)
Re-run compare.py on the frozen matcher. This is the final build. Run it 3 times so its timing is logged (section 6.10). Print the counts (clusters, facilities, review clusters, skipped edges, clusters not materialized).
Build E9: label-derived fields from the newest metric_results row, sensitivityTable and coverage computed live.
Blocking recall (blocking_recall.py, section 6.9): draw 30 holdings, you find their true counterparts by hand outside the pipeline, record them, finalize. Re-run evaluate.py so blockingRecall is filled in. If blocking recall is low, report it as measured. Do not re-tune blocking unless you are willing to redo Phase 7.
Run python -m pipeline.report (read-only, allowed after the freeze) to regenerate docs/data_report.md with blocking efficiency next to blocking recall and the logged run times. Add the machine spec by hand. Report only: never retune blocking to improve these numbers.
Tests: 22, 23.
Gate: E9 returns a non-null headline. If blocking recall isn't done, it moves to Day 12 and its field stays null.
Phase 9: Hardening (Day 10)
Contract tests for all of E1 to E12: shapes, sort orders, 400, 404, 409, 500 DATA_INTEGRITY, the null rule, flag-off behaviour for E11 and E12.
Input validation: numeric ids, escaped search wildcards, body schemas for E12.
Compose healthchecks, CI green, lockfiles pinned, dead code and the dev route gone.
Gate: all 26 tests pass in CI.
Phase 10: Docs (Day 11)
DECISIONS.md (written by you, section 9) and the README: problem and ICE context, a five-line glossary for non-finance readers (BDC, syndicated loan, fair value, par, mark), architecture, schema summary, evaluation first, the labeling approach with a link to DECISIONS.md instead of a separate methodology page, sensitivity table, an "If this ran at scale" section marked as ideation (SPEC section 14), limitations, source URL convention, docker compose up, and the data report numbers with the machine spec.
Phase 11: Buffer (Day 12)
In order: slippage from Days 4 and 5, the blocking recall check if not done, any failed gate. Splink only if everything else is done: run it on the same blocked candidate pairs with the normalized name as the only comparison column, since attributes are already enforced by blocking. State in the README whether it was built.
6. AI and matching reference
6.1 Normalization (normalize.py)
Name: fold accents, lowercase, & becomes and, strip punctuation, collapse spaces, drop a leading the, drop legal form tokens and structural tokens from config. Digits stay. If the result is empty, fall back to the cleaned name and log it.
Instrument type enum: FIRST_LIEN, SECOND_LIEN, REVOLVER, DELAYED_DRAW, UNSECURED, OTHER, from the ordered keyword lists in config (first hit wins, so a first lien delayed draw loan is DELAYED_DRAW). OTHER rows stay in normalized_holdings but never become candidates, because a catch-all cannot satisfy "same instrument type".
Exclusions: equity rows and unfunded commitments are not written to normalized_holdings (they stay in raw_holdings). Log counts by reason in the data report.
Rate parsing into (reference_rate, spread_bps, floor_bps, pik_bps): handle forms like SOFR + 5.25%, S+525, a floor in parentheses, SONIA, Fixed 11.0%, and Cash 8.5% + PIK 2.5%. A percent value becomes basis points (x100), a bare number after S+ is already basis points. Fixed rate rows get reference_rate = FIXED and NULL spread. Unparseable rows get NULLs and are counted in the data report.
Maturity: parse MM/DD/YYYY, ISO and month-year (month-year becomes month end).
Money: strip $ and commas, parentheses mean negative, apply the filer's scale. fair_value_pct_par = 100 * fair_value / principal only when principal is non-null and non-zero, else NULL. Log values outside 0 to 150. Keep the principal currency from the unit. fair_value_pct_par is NULL unless it is USD. Rows matching the filer's configured unfunded-commitment footnote pattern (per filer, in config.yaml; HPS: "unfunded loan commitment") also get NULL and UNFUNDED_COMMITMENT. Detect by text, never by footnote number. Do not use a generic "unfunded" match: ORCIC's "partially unfunded debt or equity commitment" rows sit near par and stay in.
Idempotent: upsert by holding_id. Never truncate (labels and candidate pairs reference these rows).
6.2 Blocking (block.py)
Block keys per holding, written to blocking_keys: (period, instrument_type_norm, first name_prefix_chars of the normalized name) and (period, instrument_type_norm, first token of the normalized name).
A pair is a candidate when all hold: same period_end_date, different bdc_cik, same instrument_type_norm (not OTHER), at least one shared block key, maturity within maturity_window_months when both are non-null, and spread within spread_window_bps when both are non-null. A NULL on either side skips that one gate. Pairs are stored with holding_id_a < holding_id_b.
Never compare all pairs. Log block sizes and warn above max_block_size_warn.
Expose the same predicate as a function. blocking_recall.py uses it to answer "would blocking have paired these".
6.3 Scoring (match.py)
score = token_sort_ratio(a_norm, b_norm) / 100. Name only. Maturity, spread and type decide candidacy, not the score.
Digit guard: if the multisets of digit tokens in the two normalized names differ, score = min(score, review_min - 0.01). This is what keeps "acme holdings 2" and "acme holdings" apart, since their plain ratio would land in AUTO. The cap is derived from review_min, not a separate constant.
Status: AUTO if score is at least auto_min, REVIEW if at least review_min and below auto_min (0.80 inclusive), else NO_MATCH. Every candidate pair is written, including NO_MATCH.
The baseline is the subset with equal normalized names.
6.4 candidate_pairs upsert rules
Before the freeze, re-running match.py recomputes score and status for rows in AUTO, REVIEW, NO_MATCH, deletes such rows that are no longer candidates, and leaves CONFIRMED and REJECTED rows alone. UI decisions survive a re-score.
6.5 Facility build (compare.py)
A full deterministic rebuild in one transaction. Same code for provisional (Day 7) and final (Day 9).
Load AUTO and CONFIRMED pairs for each period. Load REJECTED pairs as cannot-link constraints.
Sort edges: CONFIRMED first, then score descending, then ascending ids.
Union-find. Before joining two components, check whether any cannot-link pair would end up inside the merged component. If so, skip the edge and log it.
Components of at least 2 holdings are clusters. A cluster with two holdings from the same BDC goes to review_clusters and review_cluster_members, and is not a facility.
Among the remaining clusters, a cluster becomes a facility only if at least 2 members have a non-null fair_value_pct_par. Otherwise it is logged and skipped.
Name each cluster by the most frequent borrower_normalized among all members, ties by ascending codepoint order. Group facilities into borrowers by exact equality of that name within the period. A single-facility borrower is its own borrower.
Facility attributes: reference_rate is the most frequent member value, maturity_bucket is the earliest member maturity.
Write facility_comparisons for every member of every facility (excluded members flagged ZERO_OR_NULL_PRINCIPAL, NULL_FAIR_VALUE, NON_USD_PRINCIPAL or UNFUNDED_COMMITMENT), then facility_summary with lender_count, excluded_count, divergence_pts (max minus min, Decimal) and the flag from config cutoffs.
Delete all curated rows and insert in FK order inside one transaction. IDs are regenerated each run.
6.6 Sampling (sample_labels.py)
Tuning: draw tuning_size random pairs from measured-period candidate_pairs, regardless of UI status, with a seeded RNG. Assign a random permutation to draw_order. --min-score can bias the draw upward, because tuning pairs never count in reported metrics. Refuses once band_sizes exists (section 6.8).
Held-out: refuse to run unless a matcher_freeze row exists and the current matcher hash equals it, and refuse if band_sizes already has rows (section 6.8). Bands come from candidate_pairs.score and the frozen edges. The sampling frame is all measured-period candidate pairs minus tuning pairs. Draw heldout_per_band pairs per band (all of them if the band is smaller). Write label_samples with phase = HELDOUT and the band, and write band_sizes with the frame sizes (these are the N_b in the weighted formulas), the sample sizes and the matcher hash.
Both phases never draw a pair from another period.
6.7 Evaluation (evaluate.py)
Refuse to run unless the current matcher hash equals both matcher_freeze.matcher_config_hash and band_sizes.matcher_config_hash, or if any drawn held-out sample is unlabeled.
Read only labeled_pairs, label_samples, band_sizes, blocking_recall_checks.
Per band, count MATCH, NO_MATCH, UNSURE and n. For each UNSURE mode, m_b is the matched share (MATCH only, or MATCH plus UNSURE).
Single-band figures (AUTO-only precision, REVIEW band precision, band matchRate, blocking recall) get Wilson intervals: with p, n, z = 1.96, center = (p + z^2/2n) / (1 + z^2/n) and half = z * sqrt(p(1-p)/n + z^2/4n^2) / (1 + z^2/n).
Weighted figures use sum(m_b * N_b) formulas from SPEC section 12.6 and a bootstrap over bands: resample each band's labeled pairs with replacement, recompute, repeat bootstrap_resamples times with the fixed seed, take the 2.5th and 97.5th percentiles.
Write the E9 label-derived payload to metric_results with the config hash. unsureCount and heldOutCount come from the held-out labels. Fields not yet computable stay null.
6.8 Freeze enforcement
The freeze is a recorded step, not a convention.
The hash. config.py computes the matcher hash: sha256 over the canonical JSON of the normalization, blocking, scoring and bands config sections, plus the sha256 of each file listed in freeze.hashed_files (default normalize.py, block.py, match.py). Keep matcher logic inside those files, or add any helper they import to the list. The column name matcher_config_hash is kept for brevity, but the hash also covers those source files.
Commands.
python -m pipeline.config --hash: prints the current hash. Read-only.
python -m pipeline.config --freeze: refuses if a matcher_freeze row already exists. Otherwise inserts the single row (hash, git sha when available).
python -m pipeline.config --unfreeze: asks for confirmation, dumps held-out label_samples, held-out labeled_pairs, band_sizes and metric_results to backups/ as JSON, then deletes them and the matcher_freeze row. Tuning samples and tuning labels stay.
Enforcement, all keyed off matcher_freeze.
normalize.py, block.py and match.py refuse to run while a freeze row exists.
sample_labels.py --phase heldout refuses unless a freeze row exists and the current hash equals it. It also refuses if band_sizes already has rows. It copies the stored hash into band_sizes.
sample_labels.py --phase tuning refuses once band_sizes exists, since a new tuning pair could overlap the held-out sample.
evaluate.py refuses unless the current hash equals both matcher_freeze.matcher_config_hash and band_sizes.matcher_config_hash.
report.py only reads, so it runs after the freeze. compare.py is not part of the matcher and also runs after the freeze.
This closes the window between the Day 8 morning freeze and the afternoon draw: an edit to a hashed config key or source file in between changes the hash, and the draw refuses.
6.9 Blocking recall (blocking_recall.py)
--draw: seeded random sample of 30 measured-period holdings, printed with their raw rows.
You search the other BDCs' schedules by eye. The pipeline must not suggest counterparts.
--record <holding_id> <counterpart_id>: stores a hand-found pair. Holdings with no counterpart get no row, so n can be below 30.
--finalize: sets found_by_blocking by applying the section 6.2 predicate to each recorded pair.
6.10 Report (report.py) and the run-time log
block.py, match.py and compare.py each append one JSON line per run to docs/run_times.jsonl: module, seconds, period, config hash, git sha. This is automatic, not a flag.
python -m pipeline.report is read-only, so it runs any time, including after the freeze. It writes docs/data_report.md with ingest counts per filing (Phase 3) and, once candidate pairs exist, blocking efficiency: all_pairs (the sum of n_i * n_j over BDC pairs in the measured period), candidate_pairs, candidate_share and pairs_avoided_pct. It shows these next to blockingRecall when that exists, plus the median of the last 3 run times per module for the current config hash.
You add the machine spec (CPU, RAM, OS) to the report header by hand.
Report only (SPEC section 12.9): never in the API, never in metric_results, never a tuning target. Do not retune blocking after the freeze to improve them.
7. Endpoint implementation map
Endpoint
Reads
Writes
Day
Tests
E1
raw_filings, facility_summary, candidate_pairs, review_clusters, env MEASURED_PERIOD_END
none
7
shape
E2
canonical_borrowers, canonical_facilities, facility_comparisons
none
7
18, shape
E3
canonical_borrowers, canonical_facilities, facility_summary, facility_comparisons
none
7
shape
E4
canonical_facilities, canonical_borrowers, facility_summary, facility_comparisons
none
7
shape
E5
canonical_facilities, canonical_borrowers, facility_comparisons, facility_summary
none
7
12, 22
E6
candidate_pairs, normalized_holdings, raw_holdings, review_clusters, review_cluster_members
none
7
17, shape
E7
candidate_pairs
candidate_pairs.status, updated_at
7
13
E8
candidate_pairs
candidate_pairs.status, updated_at
7
13
E9
newest metric_results, facility_summary, counts
none
9
23
E10
raw_filings, raw_holdings (count)
none
2 and 7
shape
E11
label_samples, labeled_pairs, normalized_holdings, raw_holdings
none
6
24
E12
label_samples
labeled_pairs
6
24

Raw names come from raw_holdings.portfolio_company_raw. Source URLs come from normalized_holdings.source_url. lenderCount counts distinct BDCs among included facility_comparisons rows.
8. Test map (SPEC section 13)
Phase
Tests
2
6
3
7
4
1, 2, 3, 4, 5, 10, 11
5
15, 24
6
8, 9, 12, 13, 14, 16, 17, 18, 19, 20, 21, 22, 26
7
25
8
22, 23
9
contract tests for all of E1 to E12

Files: tests/test_normalize.py, test_match.py, test_idempotency.py, test_schema_drift.py, test_compare.py, test_evaluate.py, test_guards.py, and the API contract tests in api/tests/. One extra unit test in test_match.py, not a numbered SPEC test, checks the all_pairs formula on a fixture with 3, 2 and 4 holdings in three BDCs in one period (32 + 34 + 2*4 = 26).
9. Working rules (put in CLAUDE.md)
Read every diff. You must be able to explain every file in an interview.
You label the data. Never let any model pre-label or suggest labels.
Write the DECISIONS.md lines yourself: the two-phase design, frozen bands and per-band sample sizes, the freeze mechanism and what the matcher hash covers (config sections plus matcher source files), the crossFilingNames limitation (it uses the matcher's own normalizer, so it is independent of scores and bands but not of normalization), why 0.80 is both the fuzzy floor and the REVIEW lower edge, the digit guard, the name-only scorer, exact-name borrower grouping, why no review-confirmed figure is reported, which tag decisions were made on Day 1.
Write the edge case tests yourself (Holdings versus Holdco, digits in names, same-BDC collisions) and have the agent implement against them. Do not accept tests that just mirror the implementation.
Spot-check 10 displayed rows against the actual SEC filing by hand before calling a slice done.
Never run normalize.py, block.py or match.py after the freeze, and never paste a metric into the README that did not come from metric_results.
Never retune blocking after the freeze to improve pairs avoided or run times. Those are report-only.
10. Claim rules
Quote only numbers measured on the held-out set. Headline is AUTO-only precision plus the REVIEW band's precision, each with its interval and UNSURE range.
Say "recall given blocking" and report blocking recall separately.
Never report a figure that includes review-queue confirmations.
Never imply Splink was run unless it was. Never claim market coverage or cross-quarter results.
Pairs avoided is never quoted without blocking recall. Run times are quoted only for the frozen config and with the machine spec.

