# Diff reading order

Files changed since commit 73bc5d2 (committed since then, plus the working tree on top of HEAD `1dc1703`), from `git diff -M --numstat` and `git ls-files --others`. Order: pipeline, migrations, API, web, tests, build and CI, plans, docs. Lines is the current length of the file; +/- is added and removed lines against that commit. The last column is what to be able to explain about the file. Facts only.

## Pipeline

| File | Change | Lines | +/- | Be able to explain |
|---|---|---|---|---|
| `pipeline/blocking_recall.py` | modified | 175 | +175/-0 | The seeded draw of 30 holdings, why --record writes a pending file and --finalize writes the table, what the predicate decides, and what --search lists and leaves out. |
| `pipeline/compare.py` | modified | 279 | +30/-6 | Where the dossier columns, the signals and facility_history are written inside the single rebuild transaction, and why ids and core columns do not change. |
| `pipeline/config.yaml` | modified | 142 | +9/-0 | The new evidence section (the signal thresholds, the floor filers, the history check seed and size) and wilson_z under evaluation, and why none of these is in the matcher hash. |
| `pipeline/evaluate.py` | modified | 318 | +144/-3 | How the three precision numbers, the band weighted figures and the bootstrap are computed, why a band labeled in full is not resampled, and when it refuses to write metric_results. |
| `pipeline/evidence.py` | added | 63 | +63/-0 | The dossier arithmetic and the seven signal rules, and why a null field never fires a signal. |
| `pipeline/link_history.py` | added | 164 | +164/-0 | The link rule (EXACT_KEY, EXACT_MATURITY, the currency check), the persistence order of tests, and what the worksheet and --record do. |
| `pipeline/report.py` | modified | 320 | +70/-1 | The sections added to the data report: blocking efficiency, run time medians and the host machine. |

## Migrations

| File | Change | Lines | +/- | Be able to explain |
|---|---|---|---|---|
| `db/migrations/011_evidence_dossier.sql` | added | 21 | +21/-0 | The new facility_comparisons columns, signal_codes, and the CHECK on the seven codes; why it is additive and idempotent. |
| `db/migrations/012_history.sql` | added | 39 | +39/-0 | The four history tables, why history_build marks that F3 is built, and the unique prior holding. |

## API

| File | Change | Lines | +/- | Be able to explain |
|---|---|---|---|---|
| `api/Dockerfile` | modified | 7 | +2/-4 | Production install only and node runs src directly. |
| `api/package-lock.json` | modified | 2327 | +2/-169 | Only removals of the TypeScript packages. |
| `api/package.json` | modified | 19 | +4/-10 | ES modules, node src/index.js, no build step, vitest and supertest only. |
| `api/src/app.js` | renamed from api/src/app.ts | 67 | +67 | How routes are mounted and why E11 and E12 exist only with the flag; the error middleware. |
| `api/src/errors.js` | renamed from api/src/errors.ts | 29 | +29 | The error shape, id parsing and the search validation (repeated or over long values are 400). |
| `api/src/facilities.js` | renamed from api/src/facilities.ts | 202 | +202 | E1 to E5 including exposure, signalCount, persistence, the E5 dossier fields and the history read. |
| `api/src/index.js` | renamed from api/src/index.ts | 21 | +21 | Start up: MEASURED_PERIOD_END is required, the pool and the flag. |
| `api/src/labeling.js` | renamed from api/src/labeling.ts | 119 | +119 | E11 never selects a score, status, band, phase or draw order; E12 derives sampling_method and band server side. |
| `api/src/metrics.js` | added | 130 | +130/-0 | E9: the newest metric_results row, the live sensitivity table, coverage, evidence lift, field coverage and history links. |
| `api/src/review.js` | renamed from api/src/review.ts | 109 | +109 | E6 to E8, the status transitions and the 404 for a pair outside the measured period. |
| `api/vitest.config.js` | renamed from api/vitest.config.mts | 5 | +5 | Which files vitest runs. |

## Web

| File | Change | Lines | +/- | Be able to explain |
|---|---|---|---|---|
| `web/Dockerfile` | modified | 11 | +1/-1 | The build stage copies vite.config.js and runs vite build; nginx serves dist. |
| `web/index.html` | modified | 12 | +1/-1 | Entry script is now main.jsx. |
| `web/package-lock.json` | modified | 1546 | +0/-45 | Only removals of the TypeScript packages; npm ci must work from clean. |
| `web/package.json` | modified | 22 | +1/-4 | The build is now vite build and the TypeScript dev dependencies are gone. |
| `web/src/App.jsx` | added | 94 | +94/-0 | The shell: E1 loaded once and shared, the Review badge, search and the theme toggle. |
| `web/src/Label.jsx` | renamed from web/src/Label.tsx | 221 | +221 | The dev only labeling page: what it shows and why it never shows a score or status. |
| `web/src/api.js` | added | 35 | +35/-0 | The fetch wrapper and the contract error shape. |
| `web/src/components.jsx` | added | 258 | +258/-0 | The four page states, the RangeStat card and its recall labels, the bootstrap note, the evidence table and the two inline SVG charts. |
| `web/src/format.js` | added | 48 | +48/-0 | Display rounding and the two null wordings, Not yet measured and Not disclosed. |
| `web/src/index.css` | modified | 20 | +19/-0 | The dark mode variant tied to the toggle. |
| `web/src/main.jsx` | added | 32 | +32/-0 | The route map and why the labeling page sits outside the shell. |
| `web/src/metrics.jsx` | added | 156 | +156/-0 | How each Metrics card maps to an E9 field and how null and full bands are shown. |
| `web/src/pages.jsx` | added | 176 | +176/-0 | Overview, Borrowers, Borrower detail and Filings, and where the Outside measured quarter tag is applied. |
| `web/src/review.jsx` | added | 107 | +107/-0 | Pair and cluster cards, Confirm and Reject, the 409 handling and the local Skip. |
| `web/src/triage.jsx` | added | 138 | +138/-0 | Triage (only valid parameters are sent) and the Facility comparison page with its Evidence panel and History strip. |
| `web/src/types.js` | added | 164 | +164/-0 | The E1 to E12 shapes as JSDoc typedefs; documentation only, CONTRACT.md is the source of truth. |
| `web/vite.config.js` | renamed from web/vite.config.ts | 11 | +11 | The dev proxy to the API. |

## Tests

| File | Change | Lines | +/- | Be able to explain |
|---|---|---|---|---|
| `api/tests/app.test.js` | renamed from api/tests/app.test.ts | 23 | +23 | The no database error shape test. |
| `api/tests/contract.test.js` | added | 130 | +130/-0 | The error matrix for E1 to E12. |
| `api/tests/db.js` | renamed from api/tests/db.ts | 70 | +70 | How scratch databases are created and dropped. |
| `api/tests/labeling.test.js` | renamed from api/tests/labeling.test.ts | 306 | +306 | E11 and E12, including the out of time phase and the hidden fields. |
| `api/tests/metrics.test.js` | added | 134 | +134/-0 | E9 before and after evaluate.py, SPEC 23 and 38. |
| `api/tests/read.test.js` | renamed from api/tests/read.test.ts | 528 | +528 | E1 to E8 and E10, SPEC 12, 13, 22, 28, 31, 32 and 36. |
| `tests/conftest.py` | modified | 81 | +3/-0 | The scratch database fixtures and the optional dossier columns in the row seeder. |
| `tests/test_blocking_recall.py` | added | 166 | +166/-0 | What each blocking recall test pins: the seeded draw, record validation, finalize and the search rules. |
| `tests/test_compare.py` | modified | 490 | +94/-0 | The signal boundary tests (SPEC 29), determinism (37) and the dossier columns. |
| `tests/test_evaluate.py` | modified | 333 | +110/-1 | The refusals (25c), the three numbers, the hand computed Wilson and weighted values. |
| `tests/test_history.py` | added | 208 | +208/-0 | SPEC 33 to 35 and 37: the link rule, persistence precedence and prior quarter isolation. |
| `tests/test_migrations.py` | modified | 50 | +5/-4 | The 23 table count. |
| `tests/test_report_sections.py` | added | 37 | +37/-0 | The report sections and their numbers. |

## Build, CI and compose

| File | Change | Lines | +/- | Be able to explain |
|---|---|---|---|---|
| `.github/workflows/ci.yml` | modified | 89 | +1/-2 | The four jobs and that the API job has no build step. |
| `docker-compose.yml` | modified | 86 | +5/-0 | The web healthcheck and the service order. |

## Plans and records

| File | Change | Lines | +/- | Be able to explain |
|---|---|---|---|---|
| `CLAUDE.md` | modified | 39 | +2/-2 | The stack line and the types.js rule. |
| `CONTRACT.md` | modified | 191 | +3/-2 | The additive [v2] wording: dossier null exception, E4 and E5 fields, E9 Range, out of time object, recall labels and the E7 and E8 period rule. |
| `DECISIONS.md` | modified | 369 | +75/-5 | Sections 25 to 33: what was built and measured, with the numbers. |
| `README.md` | modified | 193 | +193/-0 | The evaluation first structure, the limits and which numbers come from which source. |
| `SPEC.md` | modified | 972 | +7/-7 | The migration 011 and 012 lines, the version table row and the table count. |
| `phase_wise.md` | modified | 445 | +1/-1 | The note on how --record and --finalize work. |

## Docs

| File | Change | Lines | +/- | Be able to explain |
|---|---|---|---|---|
| `docs/FILE_GUIDE.md` | added | 60 | +60/-0 | A one line purpose for every file. |
| `docs/blocking_recall_worksheet.md` | added | 40 | +40/-0 | The 30 drawn holdings, raw attributes only. |
| `docs/data_report.md` | modified | 89 | +37/-3 | The regenerated report, sections 6 to 8. |
| `docs/demo_script.md` | added | 25 | +25/-0 | The steps and what not to say. |
| `docs/history_link_worksheet.md` | added | 36 | +36/-0 | 30 history links with both quarters side by side. |
| `docs/overnight_log.md` | added | 56 | +56/-0 | The phase by phase log of the overnight run. |
| `docs/overnight_report.md` | added | 81 | +81/-0 | The final report of that run. |
| `docs/run_times.jsonl` | modified | 43 | +3/-0 | The three compare runs appended after the freeze. |
| `docs/spec_test_matrix.md` | added | 46 | +46/-0 | The mapping of SPEC tests 1 to 38 to test names. |
| `docs/spec_test_matrix.py` | added | 73 | +73/-0 | The script that builds the matrix and checks every name exists. |
| `docs/spot_check_sheet.md` | added | 20 | +20 | How the 10 rows were drawn and what the last column does and does not mean. |

## Deleted

`api/tsconfig.json`, `web/src/main.tsx`, `web/src/types.ts`, `web/tsconfig.json`

Screenshots in `docs/screens/` are not listed (10 images).
