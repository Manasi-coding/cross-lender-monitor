# Project Status After Day 1

Project: **Cross-Lender Private Credit Valuation Monitor**, a portfolio project for Apollo Global Management's Mumbai Technical Intern (Technology) campus drive.
It ingests SEC EDGAR BDC Schedules of Investments, resolves the same borrower and facility across filers with a measured entity-resolution pipeline (normalize, block, rapidfuzz score, review queue), and compares fair-value marks as % of par across lenders. No LLM in the pipeline.

Stack: Python 3.11 pipeline (pandas, rapidfuzz, psycopg, lxml), Node 24 + Express 5 + TypeScript API (pg), React 19 + Tailwind + React Router, PostgreSQL 16, Docker Compose v2, GitHub Actions, pytest. No ORM, parameterized SQL.

Docs: `SPEC.md` (scope, schema, evaluation, tests), `CONTRACT.md` (API E1 to E12), `phase_wise.md` (backend and AI plan), `frontend.md` (UI plan), `docs/day1_notes.md` (evidence), `DECISIONS.md` (written by the user), `Week_Wise_Plan.md` and `Week1_Detailed_Plan.md` (schedule).

---

## 1. Setup and chosen inputs

- `.env` has `MEASURED_PERIOD_END=2026-06-30` and a real `SEC_USER_AGENT`; `.env` is git-ignored.
- Verified: Docker 29.8.2, Compose v5.6.0, PostgreSQL 16.15 (via the local `postgres:16` image).
- Versions recorded: Node v24.13.0, Express 5.3.0, React 19.3.1, Tailwind 4.3.3, React Router 8.4.0, TypeScript 5.9.3 (spec says 5.x), pg 8.23.1; Python 3.11.0, lxml 6.1.3, pandas 2.3.3, rapidfuzz 3.14.6, psycopg 3.3.6. Vite with Tailwind 4.3.3 is unchecked, to be verified on first install.
- **BDC trio: ADS (Apollo Debt Solutions BDC, CIK 1837532), HPS Corporate Lending, Blue Owl Credit Income (ORCIC).**
- **Measured quarter: 2026-06-30.**

## 2. Parse strategy

- ADS is XBRL-first. Funded rows (nonzero principal) parse at 99.8% (636 of 637). All 816 schedule rows: 636 of 816 = 77.9%, the gap being unfunded commitments, equity and a few odd rows. Fair value of all rows sums exactly to the filing total (25,367,235,000).
- The earlier literal 90% rule is superseded. `phase_wise.md` now uses a funded-row rule (95%).
- HPS and ORCIC need HTML-assisted parsing: maturity is HTML-only for both, and HPS exposes instrument type only by lien class.
- HTML-to-XBRL join: HPS 796 of 798 rows (99.7%), ORCIC 515 of 515 (100%).
- Day 4 adapter work: join HTML to XBRL on (principal, cost, fair value) with thousands scale and name to break ties; drop XBRL rows with no main-schedule row; parse ORCIC maturity as month and year, set to month end. In the HTML-to-XBRL join on principal and cost, a printed dash is read as zero. This does not apply to fair value: see section 4 (SK Neptune Husky).
- ADS spot-checks against the filing (Corpuls, North American Rail, IQN Holding): checked, matches.

## 3. Currency rule

- Cost and fair value are USD for every row; principal is in the local currency for foreign loans. The unit tag on cost and fair value is unreliable (Dental Corp / Aryeh Bidco tagged CAD), so only the principal unit decides.
- ADS: 101 of 816 schedule rows (12.4%), or 101 of 636 funded rows, have non-USD principal (EUR 48, GBP 38, CAD 7, AUD 4, JPY 1, KRW 1, NOK 1, SEK 1). Example: Corpuls term loan, principal 20,000,000 EUR, cost 21,548,000 USD, fair value 22,706,000 USD, ratio 1.135, which is the FX rate showing through.
- **Rule:** `fair_value_pct_par` is NULL when principal is NULL, zero or not USD. The row is kept in `facility_comparisons` with `excluded_reason = NON_USD_PRINCIPAL`, counted in `excluded_count` and the data report, never converted. No FX is estimated: the filing has no rate, and cost over principal can't be told apart from a real markdown.
- Future work: convert principal with a dated FX source, then measure the effect on divergence. It needs its own evaluation.

## 4. HPS findings

- **ULTRA III joint venture:** 17 HPS XBRL funded rows (fair value 1,574,091,000) belong to the JV schedule, not HPS, and 5 more are fair-value-only JV commitment rows. Excluded from HPS holdings. ORCIC has 14 XBRL rows with no principal; one (BOCSO) is unexplained and labelled so.
- **Footnote (6) rows:** 214 of 755 HPS debt rows carry footnote (6): "Position or portion thereof is an unfunded loan commitment... Negative cost and fair value results from unamortized fees." 116 have negative cost or fair value; 98 are positive. Sampled negatives (Arcfield, Chord Searchlight, Carbon Topco, Fortress) were confirmed as unfunded commitments in the filing.
- **Evidence the denominator is wrong for all 214:** median fair value over principal for positive (6) rows is 0.380 (90 USD rows), against 0.987 for other HPS rows, 0.988 for ADS and 0.985 for ORCIC.
- **Decision (resolved):** fair_value_pct_par is NULL with `excluded_reason = UNFUNDED_COMMITMENT` for rows whose footnote text matches the filer's configured pattern. HPS pattern: "unfunded loan commitment". Detect by text, not footnote number. Rows are kept and flagged.
- ORCIC has 119 rows with a "partially unfunded debt or equity commitment" footnote, but their median is 0.986 (unflagged 0.985), so they stay in. A generic "unfunded" match would drop them wrongly, so patterns are per filer. ADS has none.
- No ratio-based rule: a low ratio can't be told apart from a real markdown.
- **Revolver and delayed-draw limitation (open, measured on Day 4):** HPS funded rows are typed by lien class only. Only one funded row exposes a signal in its name (CoreWeave Financing DDTL V). 461 funded HPS rows share a borrower with a revolver or delayed-draw commitment in the unfunded table, but that does not say which row is the revolver, so no row-level rule is invented. A keyword rule and measuring its effect are Day 4 work.
- Navacord's sampled negative row is preferred stock or equity, outside the funded-debt universe.
- **ADS fair value shown as a dash (SK Neptune Husky Group Sarl):** the ADS row for SK Neptune Husky Group Sarl has principal 9,588,000 and cost 9,396,000, a non-accrual footnote, and a dash for fair value in the filing HTML. The XBRL has no fair value fact for the row.
- A dash cannot be told apart from "zero" or "not reported", and the fair value sum reconciles to the filing total either way.
- **Decision:** do not read the dash as zero. The row is kept in `facility_comparisons` with `fair_value_pct_par` NULL and `excluded_reason = NULL_FAIR_VALUE`. No zero mark is manufactured. It is 1 of 637 ADS funded rows.
- Same rule for all filers: a dash on fair value is NULL, never zero, unless the filing text says the fair value is zero.

## 5. Overlap gate

- Gate reading: distinct borrower names present in at least 2 of the 3 BDCs (any two lenders can form a facility). Required minimum 30.
- Baseline: 112 names (106 USD-only), 17 in all three (15 USD-only). After excluding the 214 footnote (6) rows: 111 (105 USD-only). **Gate passes.**
- Crude cross-BDC candidate pairs (not matching): 308 baseline (ADS to HPS 137, ADS to ORCIC 48, HPS to ORCIC 123); 251 excluding negative rows; **200 excluding all 214 (6) rows** (96 distinct names).
- Overlap counts must always be reported with and without non-USD rows.

## 6. Spec changes applied

- `SPEC.md`: `principal_currency TEXT` added to `normalized_holdings`; `fair_value_pct_par` comment and the Guard paragraph (principal not null, nonzero, USD, and not flagged by the filer's footnote pattern); `excluded_reason` values `ZERO_OR_NULL_PRINCIPAL | NULL_FAIR_VALUE | NON_USD_PRINCIPAL | UNFUNDED_COMMITMENT`; edge-case rows for non-USD principal, unfunded loan commitment, and a partly-unfunded footnote with a normal ratio (ORCIC, stays in); test 11 extended; section 3.2 wording.
- `phase_wise.md`: section 1 rule, Phase 0 parse rule, section 6.1 Money bullet, section 6.5 flags, per-filer footnote pattern in the Phase 3 adapter config.
- `CONTRACT.md` E5: wording only, no shape change.
- `frontend.md` 4.5: note reads "N holdings excluded because they have no usable mark."
- The per-filer footnote pattern prompt (last spec pass, including saving `pipeline/scout_footnotes.py`) was handed to Claude Code; confirm it ran.

## 7. Current status

Day 1 gates all pass. Items that remain before closing Day 1:

1. Finish the `DECISIONS.md` section 5 rewrite (replace the "Decision deferred" bullet with the resolved decision above; update the section 7 outcome list; use 105 USD-only after the exclusion, 106 before).
2. Confirm the per-filer pattern spec pass ran and `pipeline/scout_footnotes.py` is saved.
3. Review the diff and commit (`docs/`, `phase_wise.md`, `SPEC.md`, `CONTRACT.md`, `frontend.md`, `DECISIONS.md`, `pipeline/`).

## 8. What comes next

Week 1 (Days 2 to 7), from `Week1_Detailed_Plan.md`: vertical slice, schema (18 tables), CI and contract freeze, full ingest with per-filer adapters (HTML-assisted for HPS and ORCIC, footnote patterns in config), matching pipeline, labeling tools and 100 tuning labels, facilities and API. The matcher freezes on Day 8 morning.
## 9. Day 3 decisions

- API error codes: The frozen API contract now uses NOT_IMPLEMENTED, NOT_FOUND, and INTERNAL_ERROR. These codes were not explicitly named in the earlier contract, so they are recorded here as a Day 3 contract decision.
- source_sha256 migration: source_sha256 was added to raw_filings in migration 006 rather than changing migration 001, because the original migration had already been applied.
- Idempotent ingest: Re-running ingest on the same fixture is a clean no-op. The fixture SHA-256 is also checked so that a changed source file cannot silently replace the data from the original ingest.
