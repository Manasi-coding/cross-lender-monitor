## Day 2 results (ADS vertical slice)
- raw_holdings 816 rows, fair value sum 25,367,235,000, 636 funded rows with fair value, all matching Day 1. E10 returns holdingsCount 816. Principal units kept: USD 539, EUR 48, GBP 38, CAD 7, AUD 4, SEK/KRW/JPY/NOK 1 each.
- Five rows checked against the filing HTML (amounts in thousands): SK Neptune Husky, Virgin Media Secured Finance PLC, ERC Topco, DCA Investment Holding, Hovnanian. The parser matches the filing on all five.
- GET /api/_dev/holdings now has ORDER BY holding_id.

## Findings carried to Day 4/5
1. SK Neptune Husky Group Sarl (holding 51): principal 9,588,000 and cost 9,396,000, fair value is a dash in the HTML and has no XBRL fact; non-accrual footnote. A dash cannot be told apart from "zero" or "not reported" (the sum reconciles either way). Open decision, to be recorded in DECISIONS.md by the user; until then the row is excluded as NULL_FAIR_VALUE and no zero is manufactured.
2. 32 of 816 ADS identifiers have no " Investment Type " token: instrument_type_raw is NULL on 32 rows, interest_rate_raw NULL on 64 (51 with no rate, 13 with the rate left inside the name), maturity_date_raw NULL on 62 (33 with no maturity, 29 with it left inside the name). Rows with no instrument type never become candidates, so normalize needs a deterministic fallback: parse "First Lien Secured Debt - Term Loan Interest Rate ... Maturity Date ..." from the name piece, then fall back to the XBRL maturity text fact (3 rows carry it there: the ERC revolver and 2 Legacy Service Partners rows). Log how many rows each fallback fills.
3. Equity rows can hold a share count in the principal tag with a USD unit (DCA Investment Holding common equity: "82,735 Shares"). Equity must be excluded before any % of par work. Add a test, and count equity-like rows with nonzero principal.
4. Industry for ADS (needed as labeling evidence): longest-prefix match of the identifier against the 57 industry names from the HTML "Total X" rows assigns 813 of 816 rows (56 industries). The 3 unmatched: two IW Buyer rows ("Electric Equipment" in the identifier vs "Electrical Equipment" in the HTML) and the "Heat Makes Sense KDC" row, whose industry header is not visible in its HTML table. Use a small alias map in config for these, marked manual.
5. 8 name pieces end with a trailing comma; normalization strips punctuation, no action needed.
6. The non-accrual footnote appears on 22 ADS rows (including SK Neptune, ERC Topco, DCA, Esdec, Heubach Holdings USA, Vita Global and United Site Services); these are real distressed marks and stay in. ERC Topco has cost above principal in the filing itself.
7. Hovnanian (HOV K) is an unfunded revolver commitment (no principal, negative cost and fair value); excluded by the null-principal rule.

## Day 4/5 to-do list (additions)
- normalize.py fallback parse for identifiers without "Investment Type" (item 2) with counts logged.
- XBRL text-fact maturity fallback.
- Equity-excluded-before-par test (item 3).
- Industry prefix match plus alias map (item 4).
