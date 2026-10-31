# Project closure

Status on 2026-10-31. The backend and evaluation phase is finished and ready to freeze. Demo recording is intentionally out of scope: deployment is the next stage. The matcher is frozen with hash `6b32a3b896b7556d7c9bfb6261028ebc1fb870c5608079b2b06aa1c74d2387fc`, checked before and after this work.

## What was completed

- The pipeline (ingest, normalize, block, score, classify, cluster, compare), the evaluation (held out, out of time, tuning diagnostics), the evidence dossier, the history link, the API (E1 to E12), and the web app (Overview, Borrowers, Triage, Comparison, Review, Metrics, Filings, and the dev only labeling page).
- The README was rewritten with every number unchanged. DECISIONS.md gained a reader's guide and defence notes (questions A to K) and a closure section (36). SPEC.md was corrected where it disagreed with the built schema or overstated how checks were done.
- The labeling provenance was written from repository evidence only (README and DECISIONS section 36).
- Deployment hardening: the API image runs as a non root user, the API `NODE_ENV` defaults to `production` in compose, and the database password is a variable (`POSTGRES_PASSWORD`, default `postgres` for local use).

## Verified automatically

| Check | Result |
|---|---|
| Python tests (`pytest`) | 287 passed |
| API tests (`npm test` in `api`) | 50 passed in 5 files |
| Web build (`npm run build`) | passes (there is no web test runner and no lint or type check; the build is the only check) |
| `pipeline.evaluate --dry-run` against README and E9 | AUTO 55 of 55, 55 of 60, 60 of 60; all bands, out of time table, sensitivity table and coverage equal the README |
| Hash and labels | hash equals the frozen hash; `labeled_pairs` 170; `matcher_freeze` 1 row; `blocking_recall_checks` 8 rows |
| Row guards (Q2 holdings, blocking keys, candidate pairs, label tables, freeze row, facility ids and core columns) | identical to the overnight start |
| SPEC tests 1 to 38 | all mapped to tests that exist (`docs/spec_test_matrix.md`) |
| Schema in SPEC against the live database | table and column names agree after two fixes (`signal_codes` default, `history_build`) |
| Thresholds in `config.yaml` against the documents | 0.92, 0.80, 0.65, 1.0 and 2.0 agree everywhere they are stated |
| History links | 1,260 stored links, 0 violating same BDC, borrower, type or quarters; 30 decided rows equal `history_link_checks`; E4, E5 and E9 agree with the database (four checked links followed through the API) |
| Spot check sheet | the printed name, principal, fair value, maturity and spread of all 10 rows were found in one filing table row, and fair value over principal equals the served percent of par |
| Compose and images | `docker compose config` valid; api image rebuilt, healthy, runs as `node` with `NODE_ENV=production` |

## Verified through existing evidence

- Label stability: the three label dumps (2026-10-17, 2026-10-30, 2026-10-31) equal the current table, so no label changed after them.
- The two assistant decided labels (pair 134 and 149) are recorded in DECISIONS section 24 as stated by the project owner. The repository holds no independent record of this beyond that section.
- Blocking recall NONE rows 262, 1095, 1297 and 1546: none is suspicious (`docs/blocking_recall_decisions.md`, last section).

## Completed by the project owner

- The 10 spot checks of `docs/spot_check_sheet.md`: the owner opened each cited SEC filing, located the printed borrower name and visually checked the row against the recorded principal, fair value, maturity and spread. The sheet records `Y` for owner verification and for the automated evidence on all 10 rows. This is independent human verification of those 10 rows only, not of every displayed number.

## What remains genuinely manual

- Whoever decided each of the other 168 labels: the repository cannot show it. If the owner wants a statement in the README, the owner has to supply it. Until then the README says authorship is unknown.
- The two assistant decided NO_MATCH labels remain questionable (no stored text names a different company). They were left unchanged; the README shows the effect of changing them.
- The ERC facility (22.07% of flagged exposure) rests on a provisional DIFFERENT_TRANCHE hand check.

## Final evaluation methodology

Matcher frozen by hash after about 40 diagnostic tuning labels; held out sample drawn from the frozen bands (AUTO 60 of 245, every other band labeled in full); out of time sample from the prior quarter, reported separately. Labels are MATCH, NO_MATCH and UNSURE. Precision is shown with UNSURE excluded (headline), counted as wrong, and counted as a match, each with a 95% Wilson interval. Headline is AUTO only. REVIEW is reported as counts. Review queue confirmations are in no figure. Recall is given blocking; blocking recall is measured separately from 30 randomly drawn holdings.

## Final measured results (unchanged)

- Held out AUTO precision: 55 of 55 = 100.0% (93.5% to 100.0%) with UNSURE excluded; 55 of 60 = 91.7% (81.9% to 96.4%) counting UNSURE as wrong; 60 of 60 = 100.0% (94.0% to 100.0%) counting it as a match. UNSURE is 20 of 88.
- REVIEW: 1 of 5 matched. Just below: 4 of 9. Low: 6 of 14 (counts, not precisions).
- Out of time AUTO: 28 of 30 = 93.3% (78.7% to 98.2%).
- Blocking recall: 6 of 8 = 75.0% (40.9% to 92.9%); Tier A 2 of 2; Tier B 4 of 6.
- Divergence: 93 facilities, 72 AGREEMENT, 9 MILD, 12 FLAGGED; flagged at 1, 2 and 5 points: 21, 12, 3.
- History: 1,260 of 2,127 holdings linked; 30 links checked: 29 MATCH, 1 UNSURE.

## Known limitations

- Small samples (88 held out labels, 8 blocking recall pairs), one labeler name, unknown authorship of 168 labels, and no agreement measure.
- Scoring adds little (282 of 283 AUTO pairs have equal normalized names). Tranche is not established by a MATCH, and HPS prints no instrument kind.
- Renamed borrowers (holdco, midco, merger sub, dba) are missed in the below threshold bands. OTHER type holdings (36) are never blocked.
- Unfunded commitment amounts are not parsed. Non USD principal rows are excluded (ADS 101 of 816). IDs are regenerated on each compare run.
- The weighted recall and precision intervals are bootstrap intervals that have zero width when every sampled AUTO label is a match.
- The web app has no automated tests beyond the build.

## Deployment readiness (read only audit, plus the small fixes above)

| Area | Status |
|---|---|
| Containers | db, migrate (one shot, before the API), api and web, all with healthchecks; images build from a clean copy |
| Environment | `.env.example` lists every variable the code reads (`DATABASE_URL`, `SEC_USER_AGENT`, `MEASURED_PERIOD_END`, `ENABLE_LABELING`, `PORT`) plus `POSTGRES_PASSWORD`; the API refuses to start without `MEASURED_PERIOD_END` |
| Secrets | `.env` is git ignored and no secret is committed; the only committed credentials are the local development database login `postgres` / `postgres` in compose and CI |
| Frontend and backend | the browser calls relative `/api` paths and nginx proxies them to the API: one origin, no CORS needed. A separate static host would need a reverse proxy or CORS headers |
| Hard coded localhost | only in the Vite dev proxy, the healthchecks inside the containers and the CI database URL |
| Migrations | run by the one shot service before the API; idempotent |
| Not present | a dedicated health route (the healthcheck uses `/api/filings`), nginx gzip and cache headers, authentication on E11 and E12 (off by default), TLS, backups and monitoring |
| To do at deploy time | set `POSTGRES_PASSWORD` and the database URL for the target, keep `ENABLE_LABELING=false`, put TLS in front, and decide where the pipeline jobs run |

## Files changed during this task

`.env.example`, `api/Dockerfile`, `docker-compose.yml`, `README.md`, `DECISIONS.md`, `SPEC.md`, `pipeline/report.py` (one wording line, regenerates `docs/data_report.md`), `docs/data_report.md`, `docs/demo_script.md`, `docs/FILE_GUIDE.md`, `docs/spec_test_matrix.md`, `docs/spot_check_sheet.md`, `docs/blocking_recall_decisions.md` (follow up section), `docs/history_link_decisions.md`, `docs/blocking_recall_pending.json`, `docs/project_closure.md`.

## Blockers before frontend refinement and deployment

None found. The items above under "remain genuinely manual" and "not present" are choices and owner statements, not defects.
