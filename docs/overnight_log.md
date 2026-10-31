# Overnight log

Started 2026-10-31. Matcher frozen, hash 6b32a3b896b7556d7c9bfb6261028ebc1fb870c5608079b2b06aa1c74d2387fc. No git writes.

## Needs owner decision
(Each item lists the conservative option taken.)

## Phase A: baseline
- Hash at start: equals the frozen hash.
- pytest 239 passed, API (vitest) 33 passed, web build passes (tsc and vite).
- Git status at start: only .claude/ untracked (everything earlier was committed by the owner).
- Start guards (rows and md5):
    normalized_holdings_q2 2127 af3024dc0a627671453217aac735d74c
    blocking_keys 7776 ad3d26091ad21d6f89b6afc550c96c97
    candidate_pairs 636 621cc8b8c02ef0600f2b023bbc221203
    label_samples 170 6cda08a060f94180bc44e50d18de722d
    labeled_pairs 170 a134d4ffd38d419527e28e21b445d809
    matcher_freeze 1 bb9935b1be43bf7c48fd4878433cb22c
    facility_ids 93 9cf77651f2ae0d6e21906532803bd856
    summary_core 93 ed95a4a8605bf430095e56145cf79d72
    comparisons_core 248 b10716fc25ee5f349b170c7cf7a9069f
- State found: E9 is a 501 skeleton, E4 and E5 carry only the F1 exposure fields, web has only the labeling page, evaluate.py reads labels and prints, pipeline/blocking_recall.py is an empty file, migration 009 is the last used one besides 010 (draw records).

## Phase B: Day 9 core (done)
- evaluate.py writes metric_results (+7 tests), E9 built in api/src/metrics.ts (+3 API tests), CONTRACT [v2] wording and web/src/types.ts, blocking_recall.py (+7 tests) with docs/blocking_recall_worksheet.md (30 holdings, raw attributes only), report.py gains blocking/run-time/machine sections (+3 tests), compare.py ran 3 times (1.142, 1.019, 1.139 s).
- Tests after B: pytest 256, API 36. Hash equals frozen. Guards identical to start (all 9 lines). metric_results has 1 live row.
- DECISIONS section 25 appended.
- Needs owner decision (conservative option taken):
  1. blocking_recall --record writes a pending JSON file, --finalize writes the DB (differs from phase_wise 6.9, to keep E9 null until finalize).
  2. Weighted figures: bootstrap intervals are zero width when all sampled AUTO labels are MATCH; headline stays the Wilson interval.
  3. run_times.jsonl config_hash is null on every line (cannot fix: append_run_time is in block.py, a hashed file). block and match timings predate the freeze.
  4. Live API container still runs the old image (E9 501) until the image is rebuilt in phase E.

## Phase C: F2 evidence dossier (done)
- Thresholds written to config `evidence` and DECISIONS 26 before any result. Migration 011 applied on scratch then live. evidence.py, compare.py writes dossier + signals. E4/E5/E9 updated. Tests 29, 32, 37, 38 added.
- Live: 9 of 93 facilities carry a signal; FLAGGED 12, 4 with a signal, 8 without. Guards identical (facility ids and core columns unchanged).
- Needs owner decision: pik_bps is 0 (not null) whenever no PIK is printed, so field coverage for PIK reads 100% for every BDC; left as is, noted in DECISIONS 27.

## Phase D: F3 history (done)
- Migration 012 (4 tables, 23 in all), link_history.py (rebuild, hand-check worksheet and record), compare step 9, E4/E5/E9 history fields. SPEC tests 33 to 37 added. Applied on scratch then live.
- Live: 1,260 of 2,127 holdings linked (EXACT_KEY 1,157, EXACT_MATURITY 103); 64 of 93 facilities have a prior divergence. Guards identical.
- Tests after D: see phase E entry.
- Needs owner decision: the 30-link hand check of the within-BDC link (docs/history_link_worksheet.md via --worksheet) is yours; E9 historyLinks.precision stays null until then. Worksheet not generated yet.

## Phase E: API hardening (done)
- E7/E8 404 outside the measured period (+test), search validation, contract matrix test file (9 tests), web healthcheck in compose, CI yaml parses (4 jobs), live api image rebuilt and healthy (E9 returns 200, label endpoint still 404).
- Tests after E: pytest 284 (with coverage run), API 50. Hash equals frozen. Guards identical.
- CI: docker-build job (compose build) is deferred to phase H.

## Phase F: frontend (done, with limits)
- All pages built and checked against the live API in headless Chrome (screenshots in docs/screens/, 10 files). Web build passes. No web test runner exists and none was added; no dev dependency added.
- Not done: landing page (optional), phone width and dark mode review, the 10-number spot check against SEC filings (owner).
- Live web image rebuilt and healthy (port 8080).

## Phases G and H (done)
- README, FILE_GUIDE, demo_script, spec_test_matrix, DECISIONS 25 to 31. Final: pytest 284, API 50, web build, hash equal, guards identical, compose build of all 4 images, clean copy install and build passed. See docs/overnight_report.md.
