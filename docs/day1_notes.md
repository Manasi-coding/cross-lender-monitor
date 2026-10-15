## Currency finding (Day 1, ADS 10-Q period end 2026-06-30)
- Cost and fair value are reported in USD for every row. Principal is in the local currency for foreign loans.
- Example: Corpuls Heartbeat BidCo term loan. Principal 20,000,000 EUR, cost 21,548,000 USD, fair value 22,706,000 USD. Fair value over principal is 1.135, which is the EUR rate showing through, not 113.5 percent of par.
- The unit tag on cost and fair value is not always reliable. The Dental Corp (Aryeh Bidco) row tags cost and fair value as CAD on amounts that behave like USD. Only the principal unit is used to detect non-USD rows.
- 101 of 816 schedule rows (12.4 percent) have a non-USD principal: EUR 48, GBP 38, CAD 7, AUD 4, JPY 1, KRW 1, NOK 1, SEK 1.
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

## Pending
- Ctrl+F spot-checks in the filing: Corpuls (term loan par 20,000, cost 21,548, fair value 22,706 in thousands, and the delayed draw), North American Rail, IQN Holding.
- Check whether the other two BDCs report cost and fair value in USD with local principal.
- Overlap counts must be reported both with and without non-USD rows.

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

- Schedule rows, parsed rows and parse percent use the nonzero-principal definition (rerun with summarize_parse). The non-USD and overlap columns were produced before that change by scout.py, which still counts zero-principal rows as parsed. Unverified under the new definition.
- The CIKs are those in pipeline/scout.py CANDIDATES. Name confirmation against EDGAR was not rerun in this cleanup: unverified here.
- ARCC shows 0 non-USD rows. Whether ARCC tags foreign principal with a non-USD unit is unverified.

## Three-way overlap (all rows / USD-principal rows only)
- ADS and HPS: 48 / 43
- ADS and ORCIC: 38 / 35
- HPS and ORCIC: 60 / 58
- All three: 17 / 15

The ADS pair figures match the scout overlap rerun. The HPS and ORCIC pair and the three-way figures were provided and were not rerun here: unverified in this cleanup.

## Open findings
- HPS has no instrument type in its XBRL identifier.
- Maturity is HTML only for HPS, ORCIC and BXSL.
- ORCIC carries the instrument type in the identifier.
- Reconciliation gaps for HPS and ORCIC are unexplained.
- Unfunded rows rule: rows with cost below 0 or fair value below 0 are excluded at normalization. HPS has 118 rows with negative cost and 80 with negative fair value.

## Pending
- Prompt 5c HTML feasibility.
- Ctrl+F spot-checks in the filing (Corpuls, North American Rail, IQN Holding).
- BDC pair not yet chosen. MEASURED_PERIOD_END is not yet set in .env.
