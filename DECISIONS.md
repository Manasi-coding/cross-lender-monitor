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
- Day 4 adapter work: join HTML to XBRL on (principal, cost, fair value) with thousands scale and name to break ties; drop XBRL rows with no main-schedule row. ORCIC maturity is stored as printed (M/YYYY) in the raw column and converted to the month end in normalize. In the HTML-to-XBRL join on principal and cost, a printed dash is read as zero. This does not apply to fair value: see section 4 (SK Neptune Husky).
- ADS spot-checks against the filing (Corpuls, North American Rail, IQN Holding): checked, matches.
- **ADS industry:** `industry_raw` is set by longest-prefix match of the identifier against the 57 printed "Total <industry>" names (813 of 816 rows). A manual alias map in `config.yaml` covers the other 3 rows: the two IW Buyer rows ("Electric Equipment" maps to "Electrical Equipment") and the Heat Makes Sense KDC/ONE row (maps to "Personal Care Products", the header it sits under in the table).
- **ORCIC total tie:** the loaded ORCIC fair value sum (35,713,477,000) equals the printed total (35,690,147 thousand) only after the three printed "misc. debt commitments" subtotal lines (minus 23,130, minus 73 and minus 127 thousand) are counted. Those lines are not loaded as rows.
- **ORCIC maturity:** `maturity_date_raw` keeps the printed "M/YYYY" (437 rows); normalize converts it to the month end.

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
- **HPS names:** the printed table name replaces the XBRL name, because the XBRL name carries an index (for example "Arcfield Acquisition Corp 1").
- **HPS floors:** HPS rate strings carry no floor. Floors are stated in footnote text ("The interest rate floor ... was X%" on 588 rows, "There are no interest rate floors" on 171 rows), and ORCIC has no floor data in any form.
- **Per-filer footnote patterns:** unfunded: HPS "unfunded loan commitment" (215 rows, 214 funded); ORCIC has none, because a generic "unfunded" match would flag 121 rows (119 funded) that sit near par; ADS has none. Non-accrual: "non-accrual status" for all three (ADS 22 rows, HPS 13, ORCIC 4).

## 5. Overlap gate

- Gate reading: distinct borrower names present in at least 2 of the 3 BDCs (any two lenders can form a facility). Required minimum 30.
- Baseline: 112 names (106 USD-only), 17 in all three (15 USD-only). After excluding the 214 footnote (6) rows: 111 (105 USD-only). **Gate passes.**
- Crude cross-BDC candidate pairs (not matching): 308 baseline (ADS to HPS 137, ADS to ORCIC 48, HPS to ORCIC 123); 251 excluding negative rows; **200 excluding all 214 (6) rows** (96 distinct names).
- Overlap counts must always be reported with and without non-USD rows.
- **Overlap on real ingest:** 117 names in 2 or more BDCs (109 USD-only), against 112 (106) on Day 1. Excluding the 32 ADS fallback rows reproduces the Day 1 numbers, so the change comes from those rows now having clean names.

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
- Compose db port: the compose db is published on 127.0.0.1:5432 for local pytest, and CI uses a service container.

## 10. Day 3 and Day 4 additions

- **Committed filing hashes:** `fixtures/filing_hashes.json` holds the accession and sha256 of all three filings. Ingest exits with code 2 and prints both hashes if a downloaded file differs.
- **ADS filing hash:** the re-downloaded ADS document has a different sha256 from Day 3 for the same accession (c3db46db... against ebbb7a1e...). It parses to identical content on all 816 rows; the old file was lost, so the cause is unexplained, and the new hash is the recorded one.

## 11. Day 5 decisions

- **EQUITY_POSITION and precedence:** equity rows get `excluded_reason = EQUITY_POSITION`. One reason per row, first match wins, in this order: EQUITY_POSITION, ZERO_OR_NULL_PRINCIPAL, UNFUNDED_COMMITMENT, NON_USD_PRINCIPAL, NULL_FAIR_VALUE.
- **Rows kept, not skipped:** equity and unfunded rows stay in `normalized_holdings` with their reason and a NULL `fair_value_pct_par`, so counts by reason can be reported. 2,127 rows are normalized (ADS 816, HPS 796, ORCIC 515).
- **Migration 007:** adds `non_accrual BOOLEAN NOT NULL DEFAULT FALSE` and `excluded_reason TEXT` to `normalized_holdings`. Non-accrual is a flag only, and those rows keep their marks.
- **spread_bps is the total spread:** `normalized_holdings.spread_bps` is cash plus PIK, and `pik_bps` is informational (the part already inside it). `facility_comparisons.spread_bps_total` is a copy of it, and nothing adds `pik_bps` again.
- **Test 4:** a first-lien and second-lien pair is blocked out by the type gate. It is not a candidate pair and is never stored as NO_MATCH.
- **ADS printed legal names:** ADS `portfolio_company_raw` takes the legal name printed in the HTML main-schedule table (812 of 816 rows), as HPS does. The other 4 rows have no table row and keep fallback names from the XBRL identifier. Distinct ADS names equal to an HPS or ORCIC name rose from 37 to 67.
- **Equity keyword list:** a type is EQUITY if its text, after share counts are removed, contains one of: common stock, preferred, warrant, units, membership interest, partnership interest, equity, lp interest, llc interest, class a interest. "Investment partnership" and "Investments in Joint Ventures" are not clearly ownership interests and stay OTHER. Equity rows: ADS 30, ORCIC 77, HPS 40.
- **Alias clauses:** a balanced parenthetical clause that starts with dba, d/b/a, f/k/a, fka, "formerly known as" or "doing business as" is removed from `borrower_normalized`, and a nested clause goes as one. Digits inside the clause are removed with it, digits outside stay, the raw name is unchanged, and the alias text is discarded, not used as an alternate name. 54 of the 56 affected pairs moved from NO_MATCH to AUTO. The 2 CT Technologies pairs remain because "(& Smart Holdings Corp.)" is not an alias clause. Other parentheticals such as "(US)" and "(Newfoundland)" are left alone.
- **Measured period only:** `block.py` and `match.py` run only for `MEASURED_PERIOD_END`. Rows from another period may be ingested and normalized but produce no candidate pairs, facilities or label samples. Day 5 produced 313 candidate pairs out of all_pairs 1,479,716, so pairs avoided is 99.98%. That figure is report only and is quoted only next to blocking recall, which is not yet measured.
- **Exact-match baseline:** 282 candidate pairs have equal normalized names, and all 282 are AUTO. The scorer gives 283 AUTO plus 5 REVIEW, so it adds 1 AUTO pair and 5 REVIEW pairs beyond exact equality. Band counts: 283 AUTO, 5 REVIEW, 10 JUST_BELOW, 15 LOW.
- **OTHER-typed debt rows can never match:** OTHER is never a candidate type. 11 HPS rows typed "Other Secured Debt" and 2 ORCIC rows typed "Specialty finance debt investment" are debt, and they cannot pair.
- **HPS tranche limitation:** HPS funded rows are typed by lien class only, so an HPS revolver or delayed draw is not typed as one. 461 funded HPS rows share a borrower with a revolver or delayed-draw commitment (Day 4), so a pair with an HPS holding can join different tranches of one borrower.
- **Evaluation redesign:** thresholds stay at the defaults (0.92 and 0.80, just_below 0.65, maturity 3 months, spread 50 bps). About 40 randomly drawn blocked tuning pairs are labeled for diagnostics only, to find normalization bugs, and no label moves a threshold. The held-out AUTO band is sampled at a default of 60 (adjustable), every other band at min(25, band size), so a band of 25 or fewer is labeled in full. The tuning pairs stay out of the held-out frame, and the tuning draw stays random. Reason: on Day 5 the candidate pool was 313 pairs with 283 AUTO, so about 30 pairs lay near the boundary, too few to tune on.
- **Disclosure:** normalization was iterated on Day 5 by inspecting unlabeled candidate pairs. No label informed any threshold.
- **Label limit:** a MATCH label's independent signals confirm the borrower, not the tranche, and HPS is typed by lien class only. A MATCH on a pair with an HPS holding does not establish the same tranche.
