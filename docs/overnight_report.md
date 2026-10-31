# Overnight report, 2026-10-31

Matcher hash at the start, after every phase and at the end: `6b32a3b896b7556d7c9bfb6261028ebc1fb870c5608079b2b06aa1c74d2387fc`, equal to `matcher_freeze` row 1. No git write was made. `normalize.py`, `block.py`, `match.py`, `currency.py` and the hashed config sections were not edited or run. `labeled_pairs`, `label_samples`, `candidate_pairs` and `matcher_freeze` were not written (guard below). ENABLE_LABELING is still false (`GET /api/label/next` returns 404).

## Phases

| Phase | Result |
|---|---|
| A. Baseline | Done. Hash, guards, git snapshot and test counts recorded. SPEC test matrix built (`docs/spec_test_matrix.md`). |
| B. Day 9 core | Done. `evaluate.py` writes `metric_results` (three UNSURE numbers, weighted figures with bootstrap, separate out of time object); E9 built; CONTRACT [v2] wording and `web/src/types.ts`; `blocking_recall.py` with the worksheet of 30 holdings; `compare.py` run 3 times; machine spec in the data report. Blocking recall is still null: it needs you. |
| C. F2 evidence dossier | Done. Thresholds fixed in config and DECISIONS 26 before any result. Migration 011, `evidence.py`, compare changes, E4, E5 and E9 fields. Unfunded commitment amounts are not parsed (future work). |
| D. F3 history | Done. Migration 012, `link_history.py`, compare step 9, E4, E5 and E9. The link hand check is not done: it needs you. |
| E. API hardening | Done. E7 and E8 404 outside the measured period, search validation, a contract matrix test file, a web healthcheck, CI yaml checked. |
| F. Frontend | Done, with limits. All pages built and smoke tested in headless Chrome against the live API. No web test runner exists. The optional landing page was not built. |
| G. Docs | Done. README, FILE_GUIDE, demo script, DECISIONS sections 25 to 31. |
| H. Final verification | Done. A second stack was not started (see below). |

Skipped: nothing was skipped for failure. Not built: the landing page; unfunded commitment parsing; a web test runner.

## Test counts

| Suite | Before | After |
|---|---|---|
| pytest | 239 passed | 284 passed |
| API (vitest) | 33 passed | 50 passed |
| Web | build passed | build passed (tsc and vite) |
| SPEC section 13 matrix | not built | 38 of 38 present |

New tests: `test_evaluate.py` +7, `test_blocking_recall.py` 7, `test_report_sections.py` 3, `test_compare.py` +8, `test_history.py` 20, `test_migrations.py` (table count 19 to 23); API `metrics.test.ts` 5, `contract.test.ts` 9, `read.test.ts` +5.

## SPEC section 13 matrix

`docs/spec_test_matrix.md` maps each of tests 1 to 38 to the test files and names that cover it; the script `docs/spec_test_matrix.py` checks each name exists. Result: 38 mapped, none missing, and the full runs above pass. Test 26 is covered by three tests together (load of a second quarter, the block and match period test, and the prior quarter isolation test).

## Guards

Start values (rows and md5) equal the values after every phase and at the end, for: Q2 `normalized_holdings` (2127 rows), `blocking_keys` (7776), `candidate_pairs` (636), `label_samples` (170), `labeled_pairs` (170), `matcher_freeze` (1), the 93 facility ids, the `facility_summary` core columns (id, divergence, flag) and the `facility_comparisons` core columns (id, holding, fair value). Checked after B, B2 (compare runs), C (scratch and live), D (scratch and live) and at the end. `metric_results` went from 0 to 1 row (the intended write). Facility rows gained new columns only (dossier, signals, history).

## Verification at the end

- Full pytest 284, API build and tests 50, web build, hash, guards: all pass and equal.
- `docker compose --profile tools build`: all 4 images build (migrate, pipeline, web, api).
- Clean copy check: the working tree copied without `.git`, `node_modules`, `.venv` and local data into a temp directory; `npm ci` in `api` and `web`, both builds and the compose build (project name `xcheck`) passed. The `xcheck` images were removed afterward.
- A second stack was not started: the compose file publishes fixed ports (3000, 5432, 8080) that the live stack uses, and the clean copy has no `.env` with real values. So the clean copy was checked by install, build and image build, not by running.
- CI: `ci.yml` parses (4 jobs). The commands of the pytest, API and web jobs were run locally; the docker-build job was run as a local compose build.

## Needs owner decision (conservative option taken)

1. `blocking_recall --record` writes a pending JSON file and `--finalize` writes the database. This differs from phase_wise 6.9, to keep E9 `blockingRecall` null until finalize. phase_wise.md has a one line note.
2. The bootstrap intervals for the weighted figures have zero width when every sampled AUTO label is a match; the headline stays the Wilson interval. Decide whether to keep these figures (they are marked secondary).
3. `docs/run_times.jsonl` has a null `config_hash` on every line because `block.py` (frozen) writes it. block and match times predate the freeze (2026-10-30 12:46 UTC). Compare ran 3 times after it. Decide whether to accept that or re-run block and match after an unfreeze (not done).
4. `pik_bps` is stored as 0 when no PIK is printed, so PIK field coverage reads 100% for every BDC. Left as is, with a note on the Metrics page and in DECISIONS 27.
5. The history link hand check (30 links) is yours: `docs/history_link_worksheet.md`. E9 `historyLinks.precision` stays null until then.
6. SPEC.md and the CONTRACT.md header were not edited this session and are stale in places: SPEC still lists migrations 011 and 012 as "not built" and the table count as 18 or 19; the CONTRACT header says the [v2] fields are not built. I left them for you to update.
7. The E9 Range now has a third number (`unsureExcluded`) and `bands[].matchRate` is null for bands labeled in full. Both are additive wording in CONTRACT.md. Decide if you want `matchRate` filled in for full bands instead.
8. `search` repeated or over 200 characters now returns 400 on E2 and E4 (before, a repeated value was ignored). This is additive input validation, noted in CONTRACT.md.
9. Web: there is no test runner and none was added. Phone width, dark mode and screen reader use were not reviewed.
10. The README quotes the structure word rename counts (holdco 4, dba 4, midco 2, merger sub 2, sibling 1) as my reading of the names from DECISIONS section 23. Check them before using the figures anywhere.

## What only you can do

- Blocking recall: find counterparts for the 30 holdings by hand (`docs/blocking_recall_worksheet.md`), run `python -m pipeline.blocking_recall --record <id> <id>` for each, then `--finalize`, then `python -m pipeline.evaluate`.
- The history link hand check (`python -m pipeline.link_history --record <holding> <prior> <label> --by <name>`).
- The DECISIONS.md rewrite. Sections 25 to 31 were appended by the assistant and are plain statements of what was built and measured.
- The labeling provenance paragraph in README (the line marked OWNER TO COMPLETE) and the reasons for the two NO_MATCH labels.
- Record the demo (`docs/demo_script.md`).
- Spot check 10 displayed numbers against the SEC filings through the source links.
- Read every diff, and do all git operations.

## Files changed, grouped into suggested commits

1. `evaluate: write metric_results with three UNSURE numbers and bootstrap`: `pipeline/evaluate.py`, `tests/test_evaluate.py`, `pipeline/config.yaml` (wilson_z already; evidence keys are in commit 3).
2. `E9 metrics endpoint and contract wording`: `api/src/metrics.ts`, `api/src/app.ts`, `api/tests/metrics.test.ts`, `api/tests/app.test.ts`, `CONTRACT.md`, `web/src/types.ts`.
3. `blocking recall check and report sections`: `pipeline/blocking_recall.py`, `pipeline/report.py`, `tests/test_blocking_recall.py`, `tests/test_report_sections.py`, `docs/blocking_recall_worksheet.md`, `docs/data_report.md`, `docs/run_times.jsonl`, `phase_wise.md`.
4. `F2 evidence dossier and signals`: `db/migrations/011_evidence_dossier.sql`, `pipeline/evidence.py`, `pipeline/compare.py`, `pipeline/config.yaml`, `api/src/facilities.ts`, `tests/test_compare.py`, `tests/conftest.py`, `api/tests/read.test.ts`.
5. `F3 history link and persistence`: `db/migrations/012_history.sql`, `pipeline/link_history.py`, `tests/test_history.py`, `tests/test_migrations.py`, `docs/history_link_worksheet.md`.
6. `API hardening, healthchecks and contract tests`: `api/src/errors.ts`, `api/src/review.ts`, `api/tests/contract.test.ts`, `docker-compose.yml`.
7. `frontend: all pages against the live API`: `web/src/*` (App, api, format, components, pages, triage, review, metrics, main, index.css, types), `docs/screens/`.
8. `docs: README, file guide, demo script, test matrix, overnight log and report`: `README.md`, `docs/FILE_GUIDE.md`, `docs/demo_script.md`, `docs/spec_test_matrix.md`, `docs/spec_test_matrix.py`, `docs/overnight_log.md`, `docs/overnight_report.md`, `DECISIONS.md`.

Note: `pipeline/config.yaml` and `CONTRACT.md` change in more than one phase; commit them with the first group that needs them, or with `git add -p`.
