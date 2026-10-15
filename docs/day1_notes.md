## Currency finding (Day 1, ADS 10-Q period end 2026-06-30)
- Cost and fair value are reported in USD for every row. Principal is in the local currency for foreign loans.
- Example: Corpuls Heartbeat BidCo term loan. Principal 20,000,000 EUR, cost 21,548,000 USD, fair value 22,706,000 USD. Fair value over principal is 1.135, which is the EUR rate showing through, not 113.5 percent of par.
- The unit tag on cost and fair value is not always reliable. The Dental Corp (Aryeh Bidco) row tags cost and fair value as CAD on amounts that behave like USD. Only the principal unit is used to detect non-USD rows.
- 101 of 816 schedule rows (12.4 percent) and 101 of 636 funded rows (15.9 percent) have a non-USD principal: EUR 48, GBP 38, CAD 7, AUD 4, JPY 1, KRW 1, NOK 1, SEK 1.
- Correction: an earlier note said currency cancels in percent of par. It does not, because fair value is in USD and principal is in local currency.

## Rule
fair_value_pct_par is NULL when principal is NULL, zero, or not in USD. The row is kept in facility_comparisons and flagged with excluded_reason NON_USD_PRINCIPAL. It is counted in excluded_count and in the data report. No exchange rate is estimated, because the filing contains none and cost divided by principal cannot be told apart from a real markdown (Vita Global).

## Parse decision (ADS)
- Literal 90 percent rule gave 77.9 percent (636 of 816 schedule rows with nonzero principal and fair value). The gap is rows with no principal or zero principal in the filing. An earlier breakdown of 145 unfunded commitments, 29 equity and 2 odd revolver or delayed draw rows was made before the zero-principal change and is unverified under this definition.
- Funded rows (principal not null and not zero) parse at 99.8 percent (636 of 637). Fair value of all 816 rows sums exactly to the filing total (25,367,235,000). Decision: XBRL-first for ADS.
- The earlier figures of 640 funded and 639 with fair value included 3 zero-principal rows (Camin Cargo, Invited, Poly-Wood), which are unfunded delayed draw or revolver lines with negative cost or fair value.

## Spec changes
See SPEC.md sections 3.2, 6, 11 and 13, phase_wise.md 6.1, frontend.md 4.5, CONTRACT.md E5 (wording only).

## Future work
Convert principal to USD using a dated exchange rate source, then measure how it changes divergence results. This is a new unmeasured step and needs its own evaluation.

## Scouting table (period end 2026-06-30, offline rerun on fixtures/raw/)
Schedule rows are rows with a fair value or a cost. Parsed rows have nonzero principal and a fair value. Parse percent is parsed over schedule rows (the all-rows rate). Non-USD count is parsed rows whose principal unit is not USD. Overlap is distinct ADS borrower names matched by suffix on normalized tokens, shown as all rows / USD-principal rows only.

| BDC | CIK | Schedule rows | Parsed rows | Parse percent | Non-USD | Overlap with ADS (all / USD only) |
|---|---|---|---|---|---|---|
| HPS Corporate Lending (HPS) | 0001838126 | 818 | 772 | 94.4 | 106 | 48 / 43 |
| Blue Owl Credit Income (ORCIC) | 0001812554 | 529 | 461 | 87.1 | 19 | 38 / 35 |
| Blackstone Secured Lending (BXSL) | 0001736035 | 703 | 633 | 90.0 | 110 | 32 / 28 |
| Blue Owl Capital Corp (OBDC) | 0001655888 | 603 | 298 | 49.4 | 13 | 18 / 15 |
| Ares Capital (ARCC) | 0001287750 | 1478 | 1006 | 68.1 | 0 | 16 / 16 |
| Apollo Debt Solutions (ADS, reference) | 0001837532 | 816 | 636 | 77.9 | 101 | not applicable |

- All columns use the nonzero-principal funded definition. Non-USD counts and ADS overlaps were rerun under it in Prompt 5c (pipeline/scout_overlap.py) and are unchanged from the earlier figures.
- The CIKs are those in pipeline/scout.py CANDIDATES. CIK 1837532 confirmed live on EDGAR as 'Apollo Debt Solutions BDC'; User-Agent accepted, 1 request, status 200, 0 403s.
- ARCC shows 0 non-USD rows. Whether ARCC tags foreign principal with a non-USD unit is unverified.

## Three-way overlap (all rows / USD-principal rows only)
- ADS and HPS: 48 / 43
- ADS and ORCIC: 38 / 35
- HPS and ORCIC: 60 / 58
- All three: 17 / 15

All five ADS pair figures, HPS and ORCIC (60 / 58) and the three-way (17 / 15) were rerun under the nonzero-principal definition in Prompt 5c and match.

## Open findings
- HPS has no instrument type in its XBRL identifier.
- Maturity is HTML only for HPS, ORCIC and BXSL.
- ORCIC carries the instrument type in the identifier.
- Reconciliation gaps for HPS and ORCIC are explained in the Prompt 5c results below.
- Negative cost or fair value in HPS: 119 (cost) and 85 (fair value) on XBRL schedule rows, 116 and 79 on HTML main rows. The rule to exclude them is not decided, see DECISIONS.md section 5.
- HPS footnote (6) split: 214 rows carry footnote (6), 116 with negative cost or fair value and 98 with positive cost and fair value. The 98 partially funded rows are an open decision.

## Pending
- Prompt 5c HTML feasibility: done, see Prompt 5c results.
- Ctrl+F spot-checks: checked, matches. Corpuls, North American Rail and IQN Holding parser rows match the ADS filing, including Corpuls delayed draw, NARS CAD/USD tranches and NARS negative unfunded delayed-draw row.
- HPS negative-value spot-check: checked, matches. Footnote (6) states that the position/portion is an unfunded loan commitment and that negative cost and fair value result from unamortised fees capitalised to investment cost. Sampled Arcfield, Chord Searchlight, Carbon Topco and Fortress rows therefore represent unfunded commitments and should be excluded from funded-loan normalisation. Navacord is an equity/preferred-stock row and is outside the funded-debt universe.
- Open: rule for the 98 HPS footnote (6) rows with positive cost and fair value (partially funded commitments). See Footnote (6) evidence below and DECISIONS.md section 5.
- Open: HPS row level revolver and delayed draw classification (1 of 755 funded rows exposes a signal in its name or text).

## Pair decision (chosen by you)
- BDCs: ADS (CIK 0001837532), HPS Corporate Lending (CIK 0001838126) and Blue Owl Credit Income (CIK 0001812554).
- Measured quarter: 2026-06-30. MEASURED_PERIOD_END is set in .env by you.
- Overlap gate reading: distinct names present in 2 or more of the 3 BDCs. Result: 112 (106 USD only), above the 30 name gate.
- HTML assisted parsing is required for HPS and ORCIC (maturity is HTML only for both, and HPS has no instrument type below lien class). Day 4 adapter work implied:
  - Join HTML to XBRL on (principal, cost, fair value) with thousands scale, a printed dash as zero, and name to break ties.
  - Drop XBRL rows with no main schedule row (HPS 22 from the ULTRA III note, ORCIC 14 from note tables).
  - Parse ORCIC maturity as month and year (month end).
  - HPS instrument type from section gives lien class only. Revolver and delayed draw for funded rows need a rule that is not yet decided.

## Prompt 5c results
Scripts: pipeline/scout_html.py (parse and join), pipeline/scout_reconcile.py (totals), pipeline/scout_overlap.py (currency and overlap). All read fixtures/raw/ only. Amounts in both tables are in thousands, so the join multiplies by 1000.

### A1. HTML schedule parse
| | HPS | ORCIC |
|---|---|---|
| Schedule tables (June 2026) | 24 | 22 |
| Data rows parsed | 798 (796 investments, 2 cash rows) | 515 |
| Unfunded commitment tables | 6 | 9 |

- HPS marking: single-cell rows are headers at three levels (affiliation such as "Non-Controlled/Non-Affiliated Investments", section such as "First Lien Debt", industry such as "Aerospace & Defense"). Industry subtotals, section totals and affiliation totals are rows whose name starts with "Total". The grand total is "Total Investment Portfolio", followed by a Cash section and "Total Investment Portfolio, Cash and Cash Equivalents".
- ORCIC marking: single-cell rows are affiliation, section ("Debt Investments(7)", "Equity Investments") and industry headers. Industry subtotals are unnamed rows holding only cost, fair value and percent. Named totals are "Total ... portfolio company debt investments", "misc. debt commitments" lines (negative), and "Total Investments".
- HPS sample rows (name, section, maturity, par, cost, fair value, in thousands):
  - Arcfield Acquisition Corp (4)(8)(25), First Lien Debt, 10/28/2031, 82,330, 82,154, 82,092
  - Arcfield Acquisition Corp (4)(6)(8), First Lien Debt, 10/28/2031, 13,671, (33), (39)
  - Cadence - Southwick, Inc. (4)(10)(25), First Lien Debt, 5/3/2029, 40,384, 39,805, 40,384
  - Cadence - Southwick, Inc. (4)(10)(25), First Lien Debt, 5/3/2029, 3,034, 3,002, 3,034
  - Cadence - Southwick, Inc. (4)(6)(10)(25), First Lien Debt, 5/3/2028, 17,561, 11,553, 11,708
- ORCIC sample rows:
  - DIRECTV Financing, LLC(9), First lien senior secured loan, 8/2029, 62,670, 62,767, 62,946
  - IRI Group Holdings, Inc.(3)(4)(8), First lien senior secured loan, 12/2029, 267,492, 267,180, 265,486
  - Monotype Imaging Holdings Inc.(3)(4)(8), First lien senior secured loan, 2/2031, 168,532, 167,594, 166,005
  - Horizon Avionics Buyer, LLC(3)(4)(9)(22), First lien senior secured loan, 3/2032, 152,335, 151,484, 151,438
  - Jeppesen Holdings, LLC(3)(4)(9), First lien senior secured loan, 10/2032, 16,637, 16,522, 16,388
- A printed dash in the cost or fair value column means zero, not missing. Treating it as missing dropped the HPS join to 723 of 788, so this matters for the Day 4 adapter.

### A2. Join of HTML rows to XBRL rows on (principal, cost, fair value)
| | HPS | ORCIC |
|---|---|---|
| HTML data rows joined | 796 of 798 (99.7%) | 515 of 515 (100%) |
| HTML rows matching more than one XBRL row | 11 | 2 |
| XBRL funded rows (nonzero principal and fair value) | 772 | 461 |
| Funded XBRL rows with no HTML main schedule row | 17 | 0 |

- HPS, 2 HTML rows with no XBRL row: J.P. Morgan U.S. Government Fund (332,918) and Cash (292,812). Both are in the Cash and Cash Equivalents section and are not investments.
- HPS, 17 unmatched funded XBRL rows: all appear in the ULTRA III joint venture schedule printed in the notes (same layout, total investments fair value 1,574,091). They are not HPS holdings. XBRL tags them with the same single-dimension identifier axis, so dimensions alone cannot separate them from main schedule rows.
- HPS, 11 multi-match HTML rows: 9 are zero-cost zero-fair-value equity rows that share one key, 2 are Kpler Finance SA rows with identical amounts. Name must break ties.
- ORCIC, 2 multi-match HTML rows: GT Silver Co-Invest SCSp and WP Silver Co-Invest, L.P. have identical par, cost and fair value of 2,882.

### A3. Reconciliation
| | HPS | ORCIC |
|---|---|---|
| Printed total investments fair value (thousands) | 24,178,038 | 35,690,147 |
| XBRL undimensioned total at 2026-06-30 | 24,178,038,000 | 35,690,147,000 |
| XBRL schedule row fair value sum | 25,749,012,000 | 38,969,085,000 |
| Gap, schedule sum minus filing total | 1,570,974,000 | 3,278,938,000 |

- HPS affiliation totals (fair value, thousands): Non-Controlled/Non-Affiliated 23,607,483; Non-Controlled/Affiliated 155,149; Controlled/Affiliated 415,406. They sum to 24,178,038, so the filing total is the sum of all three, not only some of them.
- HPS gap closes exactly. 22 XBRL rows have no main schedule row: 17 funded rows sum to 1,574,091,000 (the ULTRA III printed total) and 5 fair-value-only rows sum to minus 3,117,000. 1,574,091,000 minus 3,117,000 is 1,570,974,000. XBRL rows that match the main schedule sum to 24,178,038,000, equal to the filing total. The HTML data rows sum to 24,803,768 thousand, the printed "Total Investment Portfolio, Cash and Cash Equivalents"; removing the 625,730 cash rows gives 24,178,038.
- ORCIC affiliation totals (fair value, thousands): non-controlled/non-affiliated 33,674,539; non-controlled/affiliated 54,761; controlled/affiliated 1,960,847. They sum to 35,690,147, equal to "Total Investments".
- ORCIC gap closes exactly. 14 XBRL rows have no main schedule row, fair value sum 3,255,608,000. The HTML data rows sum to 35,713,477 thousand, which is 23,330 above the total because the three "misc. debt commitments" lines (minus 23,130, minus 73, minus 127) are subtotals, not data rows. 3,255,608,000 plus 23,330,000 is 3,278,938,000.
- Where the 14 ORCIC rows come from: 13 appear by name and amount in the affiliated investments roll forward note table (table 48), and 10 matches by name and amount also fall in the main schedule tables. 1 appears in neither by name and amount: Blue Owl Cross-Strategy Opportunities LLC (BOCSO), cost 1.25E+9, fair value 1.24E+9. Its origin is unexplained.
- One HPS fair-value-only row (Compsych Investments Corp., fair value 0) was not located by name and amount in the notes. It does not affect any sum.

### A4. ORCIC duplicate fair values
- 11 fair values in the XBRL schedule rows are shared by two identifiers. 9 are the same borrower under two identifiers where the second row has fair value only (no principal, no cost): LSI Financing LLC, Fifth Season Investments LLC, OCIC SLF LLC, Blue Owl Cross-Strategy Opportunities 2025-1 LLC, OWL-HP FINANCE LLC, Blue Owl Credit SLF LLC, Wingspire Capital Holdings LLC, LSI Financing 1 DAC, Blue Owl Leasing LLC. Seven of these are the seven pairs noted earlier; LSI Financing 1 DAC and Blue Owl Leasing LLC were not on that list.
- In the HTML main schedule each of the 9 appears once as a data row (its unnamed industry subtotal repeats the amount). The second XBRL identifier comes from the affiliated investments roll forward note table.
- The other 2 shared fair values are different borrowers with identical amounts (Saber Parent Holdings and Snowbird Manager LP at 4,345; GT Silver and WP Silver at 2,882). Each appears as 2 rows in the HTML, so they are separate holdings.

### A5. Apex Group Treasury and Oak Funding (HPS)
- Both are real investments in the main schedule, not cash equivalents. The Cash section holds only the J.P. Morgan U.S. Government Fund and Cash.
- Apex Group Treasury LLC: First Lien Debt, Commercial Services & Supplies, SF + 3.50%, maturity 2/27/2032, par 13,412, cost 13,305, fair value 12,740.
- Oak Funding LLC: First Lien Debt, Financial Services, maturity 12/2/2032. Funded row par 199,943, cost 198,108, fair value 196,756. Unfunded row par 19,556, cost (187), fair value (312), also listed in the unfunded commitments table as a "1st Lien Senior Secured Delayed Draw Loan".

### A6. Missing maturity and instrument type
- HPS: 41 of 796 investment rows lack a maturity date: 40 in Equity Investments and 1 in Investments in Joint Ventures. All 755 debt rows have one.
- ORCIC: 78 of 515 rows lack a maturity date, all equity style (LP Interest 17, Specialty finance equity investment 9, Class A Units 6, Common Units 5, and 41 others across preferred, warrants, LLC interests and common). No debt row lacks one.
- XBRL has a maturity for 0 of 772 HPS funded rows and 0 of 461 ORCIC funded rows. For these two filers maturity exists only in the HTML table. ORCIC prints month and year only (for example 8/2029).
- HPS has no row level instrument type in XBRL (0 of 772) or in the HTML table. The only HTML signal is the section: First Lien Debt 711 rows, Structured Finance Investments 20, Other Secured Debt 11, Unsecured Debt 11, Second Lien Debt 2, Equity Investments 40, Joint Ventures 1. Term loan versus revolver versus delayed draw is not available for funded HPS rows.
- ORCIC has the type in XBRL for 456 of 461 funded rows and in every HTML row (48 distinct values).

### B7. Currency and overlap (nonzero-principal funded definition)
- HPS: 772 funded rows, 106 with non-USD principal (EUR 47, GBP 28, AUD 13, CAD 9, SEK 3, NZD 2, NOK 2, SGD 1, JPY 1). All 106 have cost and fair value unit tags of USD. Median fair value over principal: EUR 1.118, GBP 1.308, USD rows 0.977.
- ORCIC: 461 funded rows, 19 with non-USD principal (EUR 10, GBP 5, CAD 3, AUD 1). All 19 have cost and fair value tagged USD. Median fair value over principal: EUR 1.128, GBP 1.307, USD rows 0.985.
- For both filers cost and fair value are USD while principal is local currency, as for ADS. The currency rule applies unchanged.
- Non-USD funded counts for the other filers: BXSL 110, OBDC 13, ARCC 0 (ARCC unit tagging unverified).
- Overlap with ADS (all / USD only): HPS 48 / 43, ORCIC 38 / 35, BXSL 32 / 28, OBDC 18 / 15, ARCC 16 / 16. Pairs not involving ADS: HPS and ORCIC 60 / 58, BXSL and OBDC 39 / 39, HPS and BXSL 39 / 35, ORCIC and OBDC 203 / 194. Restricting HPS and ORCIC to rows confirmed in the main HTML schedule changes only the HPS and BXSL pair, to 38 / 34.

### Project gate: at least 30 overlapping borrower names in total
"In 2 or more" counts distinct names present in at least two of the three BDCs. "In all three" counts names present in every BDC.

| BDC set | In 2 or more (all / USD) | Meets 30 | In all three (all / USD) | Meets 30 |
|---|---|---|---|---|
| ADS, HPS, ORCIC | 112 / 106 | yes | 17 / 15 | no |
| ADS, BXSL, OBDC | 73 / 66 | yes | 8 / 8 | no |

The gate wording "overlapping borrower names in total" is read as the first reading. Under the all three reading neither set meets it. Facilities need at least 2 lenders, so the first reading is what feeds facility building, while the second limits three-way facilities. Which reading applies is your call.

### Still unexplained
- Origin of the BOCSO row in ORCIC (cost 1.25E+9, fair value 1.24E+9).
- Location of the Compsych Investments Corp. fair-value-only row of 0 in HPS.
- Why OBDC has only 298 funded rows out of 603 schedule rows (49.4%): not investigated.
- BXSL HTML feasibility (maturity and instrument type are both absent from its XBRL) has not been tested.

## Day 1 final close-out
Script for items 1 to 3: pipeline/scout_close.py (read only, fixtures only). Versions were read with npm view and Python metadata on this machine.

### 1. Dropped XBRL rows (already recorded, one addition)
The counts and sums are already in "Prompt 5c results" A2 and A3: HPS 22 rows (17 with nonzero principal, fair value sum 1,574,091,000; 5 fair value only, sum minus 3,117,000), ORCIC 14 rows (0 with nonzero principal, fair value sum 3,255,608,000). Rerun in scout_close.py gives the same figures. Addition, what they are:
- HPS 17 rows: real funded loan rows (borrower, principal, cost, fair value all present), but they belong to the ULTRA III joint venture schedule, not to HPS. Zero principal rows: 0. Aggregate rows: none seen (each carries a borrower name).
- HPS 5 rows: fair value only (no principal, no cost), the fair values of the joint venture's unfunded commitments.
- ORCIC 14 rows: none has principal, so none is a funded row and none is zero principal. 13 are borrower level fair value only rows from the affiliated investments roll forward. Blue Owl Cross-Strategy Opportunities LLC (BOCSO) has cost 1.25E+9 and fair value 1.24E+9. Whether it is an aggregate is unexplained.

### 2. HPS instrument type signals among funded rows
- Funded HPS rows (principal nonzero, fair value present) in the main schedule: 755.
- Rows whose name, identifier or HTML cell text contains "revolv", "delayed" or "ddtl": 1. It is CoreWeave Financing DDTL V, LLC, under First Lien Debt, par 2,500, cost 863, fair value 942 (thousands).
- Rows with negative cost or negative fair value (unfunded style): 116.
- Rows whose borrower name appears in the unfunded commitments table with a revolving or delayed draw commitment type: 461. By section header: First Lien Debt 455, Other Secured Debt 6. Commitment types seen: 1st Lien Senior Secured Revolving Loan 382, 1st Lien Senior Secured Delayed Draw Loan 239, Other Secured Debt Delayed Draw Loan 6 (a borrower can have both types, so these add to more than 461).
- All 116 negative rows are among the 461. The link is by borrower, so it does not say which of a borrower's funded rows is the revolver or the delayed draw. No rule is chosen here.
- Samples (name, section, par, cost, fair value in dollars, unfunded type of the borrower):
  - Arcfield Acquisition Corp (4)(8)(25), First Lien Debt, 82,330,000, 82,154,000, 82,092,000, Revolving Loan
  - Arcfield Acquisition Corp (4)(6)(8), First Lien Debt, 13,671,000, minus 33,000, minus 39,000, Revolving Loan
  - Cadence - Southwick, Inc. (4)(10)(25), First Lien Debt, 40,384,000, 39,805,000, 40,384,000, Revolving Loan
  - Cadence - Southwick, Inc. (4)(10)(25), First Lien Debt, 3,034,000, 3,002,000, 3,034,000, Revolving Loan
  - Cadence - Southwick, Inc. (4)(6)(10)(25), First Lien Debt, 17,561,000, 11,553,000, 11,708,000, Revolving Loan
  - Carbon Topco, Inc. (4)(6)(9), First Lien Debt, 9,588,000, minus 134,000, minus 68,000, Revolving Loan
  - Carbon Topco, Inc. (4)(9)(25), First Lien Debt, 40,837,000, 40,247,000, 40,516,000, Revolving Loan
  - Fastener Distribution Holdings, LLC (4)(9)(25), First Lien Debt, 74,685,000, 74,115,000, 74,490,000, Delayed Draw Loan
  - Fastener Distribution Holdings, LLC (4)(6)(9)(25), First Lien Debt, 28,263,000, 10,604,000, 10,771,000, Delayed Draw Loan
  - Fortress Acquisitionco, Inc. (4)(9)(25), First Lien Debt, 123,421,000, 122,245,000, 120,867,000, Revolving Loan

### 3. Rough facility level overlap (crude estimate, not matching)
Scope: ADS, HPS and ORCIC at 2026-06-30. Rows: USD principal, nonzero principal, fair value present. HPS and ORCIC are limited to rows in the main HTML schedule (the 22 and 14 dropped rows are excluded). Predicate: lowercased names equal after dropping llc, inc, corp, lp, ltd, plc, holdings, holdco (for ADS the name carries an industry prefix, so the other name must equal the tail of the ADS tokens); same lien class when both are known; maturity within 92 days when both present (ORCIC month and year taken as month end); total cash spread within 50 bps when both present (PIK not added, so this differs from the planned rule).
Rows used: ADS 535, HPS 649, ORCIC 442.

| BDC pair | Name equal | Plus lien class | Plus maturity | Plus spread | Distinct names |
|---|---|---|---|---|---|
| ADS and HPS | 167 | 167 | 151 | 137 | 43 |
| ADS and ORCIC | 61 | 58 | 53 | 48 | 27 |
| HPS and ORCIC | 178 | 170 | 141 | 123 | 58 |
| Total | 406 | 395 | 345 | 308 | |

- Cross-BDC candidate pairs after all gates: 308. Distinct borrower names across all pairs: 101.
- Excluding rows with negative cost or fair value (unfunded style): 251 pairs, 99 distinct names.
- This is a crude estimate. It uses a pair loop with no blocking keys, so it is not the matcher and is not a metric. Lien class is the only type signal, so revolver and term loan rows of one borrower are not separated, and some counted pairs may be revolver to term loan.

### 4. Versions
| Item | Value | Source |
|---|---|---|
| Node | v24.13.0, LTS line Krypton | node --version, process.release.lts |
| npm | 11.6.2 | npm --version |
| Express | 5.3.0 (latest 5.x; 4.22.3 is the 4.x line) | npm view express |
| React and React DOM | 19.3.1 | npm view react, react-dom |
| Tailwind CSS | 4.3.3 | npm view tailwindcss |
| React Router | 8.4.0 (peer react at least 19.2.7, node at least 22.22.0, both met) | npm view react-router |
| TypeScript | 5.9.3 (latest 5.x; spec says 5.x; npm latest is 7.0.2, not checked for compatibility) | npm view typescript |
| pg | 8.23.1 | npm view pg |
| Python | 3.11.0 | python --version |
| lxml, pandas, rapidfuzz, psycopg | 6.1.3, 2.3.3, 3.14.6, 3.3.6 (psycopg-binary 3.3.6) | importlib.metadata, matches requirements.txt |
- Docker: 29.8.2 — verified
- Docker Compose: v5.6.0 — verified
- PostgreSQL Docker image: 16.15 — verified

Recommended pins for the Day 3 lockfiles: express 5.3.0, react 19.3.1, react-dom 19.3.1, tailwindcss 4.3.3, react-router 8.4.0, typescript 5.9.3, pg 8.23.1. Vite 8.3.4 is the npm latest bundler, compatibility with Tailwind 4.3.3 and React 19.3.1: not verified. Python is 3.11.0, so the Docker image tag should be a 3.11.x patch release chosen on Day 3.

Verified: Docker 29.8.2, Docker Compose v5.6.0, PostgreSQL 16.15.

### 5. SEC access code check: pass
- User-Agent from env: pipeline/ingest.py line 34 reads SEC_USER_AGENT, lines 35 to 39 raise if it is empty, line 44 sets it on the session. Pass.
- Rate limit: line 41 sets the minimum interval to 1 divided by config max_requests_per_second (5, so 0.2 seconds), lines 49 to 54 sleep under a lock before each request, line 59 calls it before every get. Config is read from pipeline/config.yaml by load_sec_config (lines 25 to 27). Pass.
- Backoff: line 42 reads backoff_seconds (1, 2, 4, 8) from config, lines 57 to 69 retry on 429 and 5xx and sleep backoff[i] after each failed attempt, giving 5 attempts. A 403 raises immediately (lines 64 to 65). Pass.
- All other network use goes through SecClient (scout.py line 223, download_filing line 118 to 121). No direct requests or urllib call outside ingest.py. No test covers this yet (tests/ is empty).

### 6. Gate check
- (a) ADS holdings with nonzero principal and fair value: 636, at least 50. Pass.
- (b) Overlapping names across ADS, HPS and ORCIC, USD only, in 2 or more BDCs: 106 (Prompt 5c, pipeline/scout_overlap.py), at least 30. Pass. The crude estimate above gives 101 distinct names after the maturity and spread gates, also at least 30.
- Names in all three BDCs, USD only: 15, below 30, as recorded under the gate reading you chose.

### 7. Docs consistency
Three phase_wise.md edits made as written: section 1 NULL rule now includes "not in USD"; Phase 0 parse rule now uses 95% of funded rows; section 6.5 flags now include NON_USD_PRINCIPAL. All three quotes were found exactly once.

## Footnote (6) evidence
Script: pipeline/scout_fn6.py (read only, fixtures only). No recommendation is stated here. The rule is an open decision, see DECISIONS.md section 5.

### Scope
- HPS main schedule debt rows with nonzero principal and fair value: 755. Footnote (6) rows: 214 (116 with negative cost or fair value, 98 with positive cost and fair value).
- Footnote (6) is detected as the text "(6)" inside the HTML row name. Rows with USD principal: 649 of 755. Of the 98 positive rows, 90 have USD principal and 8 do not.
- Ratio statistics below use USD principal rows only, because fair value is in USD and principal is local currency for the others.

### c. What footnote (6) says (exact quote from the HPS 10-Q)
"(6)Position or portion thereof is an unfunded loan commitment, and no interest is being earned on the unfunded portion, although the investment may be subject to unused commitment fees. Negative cost and fair value results from unamortized fees, which are capitalized to the investment cost."

### a. Fair value over principal and cost over principal
Plain fractions, 1.000 is par. Percentiles use linear interpolation.

| Group | n | FV/par p10 | FV/par median | FV/par p90 | Cost/par p10 | Cost/par median | Cost/par p90 |
|---|---|---|---|---|---|---|---|
| HPS footnote (6), positive | 90 | 0.115 | 0.380 | 0.819 | 0.112 | 0.383 | 0.822 |
| HPS footnote (6), negative (reference) | 100 | -0.026 | -0.011 | 0.000 | -0.014 | -0.009 | -0.004 |
| HPS without footnote (6) | 459 | 0.905 | 0.987 | 1.000 | 0.983 | 0.992 | 0.999 |
| ADS | 535 | 0.896 | 0.988 | 1.002 | 0.967 | 0.990 | 0.999 |
| ORCIC (main schedule) | 418 | 0.858 | 0.985 | 1.000 | 0.984 | 0.995 | 1.000 |

### b. Five of the 98 positive rows (every 20th, amounts in thousands)
| Name | Principal | Cost | Fair value | Principal unit |
|---|---|---|---|---|
| Cadence - Southwick, Inc. (4)(6)(10)(25) | 17,561 | 11,553 | 11,708 | USD |
| NRO Holdings III Corp. (4)(6)(9)(24) | 100 | 82 | 82 | USD |
| Aryeh Bidco Investment Ltd (4)(5)(6)(9)(39) | 24,551 | 1,974 | 1,765 | CAD |
| Global Service GmbH (4)(5)(6)(7)(30) | 4,051 | 212 | 210 | EUR |
| Huskies Parent Inc (4)(6)(9)(24) | 1,000 | 112 | 28 | USD |

Footnote (6) text for all five is the quote above. In these five, cost over principal is 0.66, 0.82, 0.08, 0.05 and 0.11, and fair value over cost is 1.01, 1.00, 0.89, 0.99 and 0.25. Aryeh Bidco (CAD) and Global Service (EUR) have non-USD principal, so their cost over principal mixes currencies.

### d. Overlap gate and crude pair count under three variants
Overlap gate: distinct names in 2 or more of ADS, HPS and ORCIC, nonzero principal funded rows (same method as pipeline/scout_overlap.py; the baseline reproduces 112 and 106).

| Variant | HPS names | In 2 or more (all / USD) | In all three (all / USD) |
|---|---|---|---|
| Baseline, all HPS main rows | 350 | 112 / 106 | 17 / 15 |
| Exclude all 214 footnote (6) rows | 344 | 111 / 105 | 17 / 15 |
| Exclude only the 116 negative rows | 350 | 112 / 106 | 17 / 15 |

Crude cross-BDC candidate pairs (name equal, lien class, maturity within 92 days, spread within 50 bps; USD principal, nonzero principal). This is a crude estimate, not matching.

| Variant | HPS USD rows | Pairs | ADS-HPS | ADS-ORCIC | HPS-ORCIC | Distinct names |
|---|---|---|---|---|---|---|
| Baseline | 649 | 308 | 137 | 48 | 123 | 101 |
| Exclude all 214 footnote (6) rows | 459 | 200 | 76 | 48 | 76 | 96 |
| Exclude only the 116 negative rows | 549 | 251 | 105 | 48 | 98 | 99 |

Excluding the 98 positive rows removes 51 pairs (251 to 200) and 3 distinct names (99 to 96). The overlap gate stays above 30 in every variant.

### e. Footnote text containing "unfunded" in ADS and ORCIC (read only, no decision)
Method: inline XBRL footnotes (ix:footnote) linked by ix:relationship to the principal, cost or fair value facts of each investment identifier at 2026-06-30. A row is counted when any linked footnote text contains "unfunded". Detection is by text, not by footnote number. Check on HPS: the same method gives 214 funded rows (116 negative, 98 positive), equal to the footnote (6) count above. Rows counted are funded rows (nonzero principal and fair value).

| Filer | Funded rows | With an "unfunded" footnote | Negative cost or fair value | USD principal |
|---|---|---|---|---|
| ADS | 636 | 0 | 0 | 0 |
| ORCIC | 461 | 119 | 0 | 116 |
| HPS (check) | 772 | 214 | 116 | 190 |

- ADS: 5 footnotes mention "unfunded" (for example "Includes unfunded commitments measured at fair value of $(46,746)."). They link to 47 facts, all in 1 context with no investment identifier, so no ADS investment row carries one. The ADS negative unfunded delayed draw row (NARS) has no principal and is not a funded row.
- ORCIC: 4 footnotes mention "unfunded". Two are footnote (22): "Position or portion thereof is a partially unfunded debt or equity commitment. See “Note 8 — Commitments and Contingencies.”" Two are footnote (23): "The negative cost and fair value results from unamortized fees, which are capitalized to the investment cost of unfunded commitments, if any." No funded ORCIC row with nonzero principal has negative cost or fair value.
- ORCIC fair value over principal, USD principal rows: with the "unfunded" footnote n 116, p10 0.899, median 0.986, p90 1.000; without it n 326, p10 0.858, median 0.985, p90 1.000. Cost over principal: with 0.971, 0.992, 0.999; without 0.985, 0.995, 1.000.
- ORCIC five sample rows (principal, cost, fair value in dollars, all USD principal):
  - Horizon Avionics Buyer, LLC (dba Acron Aviation), first lien senior secured loan, 152,335,000, 151,484,000, 151,438,000
  - STS PARENT, LLC (dba STS Aviation Group), first lien senior secured revolving loan, 11,828,000, 11,780,000, 11,641,000
  - OAC Holdings I Corp. (dba Omega Holdings), first lien senior secured revolving loan, 1,470,000, 1,455,000, 1,431,000
  - MAJCO LLC (dba Big Brand Tire & Service), first lien senior secured loan, 488,156,000, 485,246,000, 479,815,000
  - McQueen Bidco PTY LTD. (dba Infomedia), first lien senior secured revolving loan, 749,000, 844,000, 794,000
- Two facts, stated without a decision: the ORCIC footnote wording is "partially unfunded debt or equity commitment", which differs from the HPS wording "is an unfunded loan commitment". Under a plain text match for "unfunded", 119 ORCIC funded rows would be flagged, and they sit at about par (median fair value over principal 0.986), unlike the 98 HPS positive rows (median 0.380).
- Open Day 4 implementation note: the UNFUNDED_COMMITMENT rule is a per-filer configured footnote pattern, not a generic "unfunded" match. HPS pattern: "unfunded loan commitment" (214 rows: 116 negative, 98 positive). ORCIC and ADS: no pattern, because a generic match would flag 119 ORCIC rows near par (median fair value over principal 0.986) and 0 ADS rows. The pattern belongs in each filer adapter's config, and each filer fixture needs one row with and one without the footnote. Reproduced by pipeline/scout_footnotes.py (read only): HPS 214, ORCIC 119 under a generic match and 0 under the configured pattern, ADS 0 funded rows.
