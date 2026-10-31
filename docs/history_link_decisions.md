# History link decisions

Labels in this file were decided by an AI assistant (Claude Code) from the raw attributes in `docs/history_link_worksheet.md`, using the rules below, not by hand. They were recorded with `link_history --record ... --by "Claude Code (AI assistant)"`.

## Rules

- Each of the 30 links was read from both quarters' raw name, instrument text, maturity, interest rate and principal.
- MATCH needs the same borrower, the same instrument kind (the printed instrument text), the same maturity and the same rate base (S, SF and SOFR are one base, P is Prime, SONIA and EURIBOR stay distinct). A different spread, PIK amount or principal is not a reason to refuse a MATCH.
- If the rate base cannot be read, or anything else cannot be confirmed, the label is UNSURE. A different borrower, kind, maturity or base is NO_MATCH.
- No link logic was changed, and no blocker or matcher output was read.

## Result: 29 MATCH, 0 NO_MATCH, 1 UNSURE (30 links)

| Holding | Prior holding | Rule | BDC | Name | Label | Reason |
|---|---|---|---|---|---|---|
| 71 | 2204 | EXACT_KEY | Apollo Debt Solutions BDC | Coretrust Purchasing Group LLC | MATCH | Same name, same instrument text (First Lien Secured Debt - Revolver), same maturity (10/01/2029) and same rate base (SOFR).Spread S+675 now against S+525 before: same base, a spread change is not evidence of a different position. |
| 122 | 2263 | EXACT_KEY | Apollo Debt Solutions BDC | Fire Flow Intermediate Corporation | MATCH | Same name, same instrument text (First Lien Secured Debt - Term Loan), same maturity (07/10/2031) and same rate base (SOFR). |
| 213 | 2348 | EXACT_KEY | Apollo Debt Solutions BDC | One Silver Serve, LLC | MATCH | Same name, same instrument text (First Lien Secured Debt - Revolver), same maturity (12/18/2028) and same rate base (SOFR). |
| 263 | 2401 | EXACT_KEY | Apollo Debt Solutions BDC | GC Waves Holdings, Inc. | MATCH | Same name, same instrument text (First Lien Secured Debt – Team Loan), same maturity (10/04/2030) and same rate base (SOFR). |
| 295 | 2433 | EXACT_MATURITY | Apollo Debt Solutions BDC | Froneri US, Inc | MATCH | Same name, same instrument text (First Lien Secured Debt - Term Loan), same maturity (09/30/2031) and same rate base (SOFR).Linked by exact maturity because Froneri US has several rows; maturity 09/30/2031 and S+225 are equal. |
| 310 | 2445 | EXACT_KEY | Apollo Debt Solutions BDC | Genesee & Wyoming Inc. | MATCH | Same name, same instrument text (First Lien Secured Debt - Term Loan), same maturity (04/10/2031) and same rate base (SOFR).Principal 10,203,000 now against 25,718,000 before: principal is not evidence. |
| 358 | 2493 | EXACT_KEY | Apollo Debt Solutions BDC | OMH-Healthedge Holdings, Inc. | MATCH | Same name, same instrument text (First Lien Secured Debt - Revolver), same maturity (04/01/2030) and same rate base (SOFR). |
| 395 | 2532 | EXACT_KEY | Apollo Debt Solutions BDC | Goldeneye Parent, LLC | MATCH | Same name, same instrument text (First Lien Secured Debt - Term Loan), same maturity (03/31/2032) and same rate base (SOFR). |
| 517 | 2643 | EXACT_KEY | Apollo Debt Solutions BDC | Ideal Components Acquisition, LLC | MATCH | Same name, same instrument text (First Lien Secured Debt - Term Loan), same maturity (06/30/2032) and same rate base (SOFR). |
| 540 | 2660 | EXACT_KEY | Apollo Debt Solutions BDC | Gannett Holdings, LLC | MATCH | Same name, same instrument text (First Lien Secured Debt - Term Loan), same maturity (10/15/2029) and same rate base (SOFR).Principal 14,644,000 now against 190,409,000 before: principal is not evidence, and every printed attribute is equal. |
| 575 | 2687 | EXACT_KEY | Apollo Debt Solutions BDC | Jazz AH Holdco, LLC | MATCH | Same name, same instrument text (First Lien Secured Debt – Delayed Draw), same maturity (04/02/2029) and same rate base (SOFR). |
| 616 | 2392 | EXACT_KEY | Apollo Debt Solutions BDC | Actium Midco 3 | MATCH | Same name, same instrument text (First Lien Secured Debt - Delayed Draw), same maturity (08/30/2031) and same rate base (SONIA). |
| 776 | 2880 | EXACT_KEY | Apollo Debt Solutions BDC | Biamp | MATCH | Same name, same instrument text (First Lien Secured Debt - Revolver), same maturity (04/30/2030) and same rate base (Prime). |
| 795 | 2894 | EXACT_KEY | Apollo Debt Solutions BDC | Lindstrom, LLC | MATCH | Same name, same instrument text (First Lien Secured Debt – Revolver), same maturity (12/30/2032) and same rate base (SOFR).Principal is blank now and 1,865,000 before: principal is not evidence. |
| 899 | 3002 | EXACT_KEY | HPS Corporate Lending Fund | Fortis 333 Inc | MATCH | Same name, same instrument text (First Lien Debt), same maturity (3/27/2032) and same rate base (SOFR).Spread SF + 3.25% now against SF + 3.50% before: same base. HPS prints First Lien Debt for every kind, in both quarters, so the kind is the same printed text but cannot be read more closely. |
| 904 | 3007 | EXACT_KEY | HPS Corporate Lending Fund | Allied Universal Holdco LLC | MATCH | Same name, same instrument text (First Lien Debt), same maturity (8/20/2032) and same rate base (SOFR). HPS prints First Lien Debt for every kind, in both quarters, so the kind is the same printed text but cannot be read more closely. |
| 997 | 3102 | EXACT_KEY | HPS Corporate Lending Fund | Bright Light Buyer, Inc. | MATCH | Same name, same instrument text (First Lien Debt), same maturity (11/8/2029) and same rate base (SOFR). HPS prints First Lien Debt for every kind, in both quarters, so the kind is the same printed text but cannot be read more closely. |
| 1207 | 3324 | EXACT_MATURITY | HPS Corporate Lending Fund | Acrisure LLC | MATCH | Same name, same instrument text (First Lien Debt), same maturity (6/21/2032) and same rate base (SOFR).Linked by exact maturity because Acrisure LLC has several rows; maturity 6/21/2032 and SF + 3.25% are equal. HPS prints First Lien Debt for every kind, in both quarters, so the kind is the same printed text but cannot be read more closely. |
| 1373 | 3485 | EXACT_MATURITY | HPS Corporate Lending Fund | Bottomline Technologies, Inc. | UNSURE | No interest rate is printed in either quarter, so the rate base cannot be compared; name, instrument text and maturity (5/15/2028) are the same. |
| 1644 | 3756 | EXACT_KEY | Blue Owl Credit Income Corp. | ConnectWise, LLC | MATCH | Same name, same instrument text (First lien senior secured loan), same maturity (9/2028) and same rate base (SOFR). |
| 1649 | 3761 | EXACT_KEY | Blue Owl Credit Income Corp. | DuraServ LLC | MATCH | Same name, same instrument text (First lien senior secured revolving loan), same maturity (6/2030) and same rate base (SOFR).Spread S+ 5.00% now against S+ 4.75% before: same base. |
| 1668 | 3784 | EXACT_KEY | Blue Owl Credit Income Corp. | Conair Holdings LLC | MATCH | Same name, same instrument text (First lien senior secured loan), same maturity (5/2028) and same rate base (SOFR). |
| 1716 | 3837 | EXACT_KEY | Blue Owl Credit Income Corp. | First Eagle Holdings, Inc. | MATCH | Same name, same instrument text (First lien senior secured loan), same maturity (8/2032) and same rate base (SOFR). |
| 1744 | 3864 | EXACT_KEY | Blue Owl Credit Income Corp. | The Better Being Co., LLC (fka Nutraceutical International Corporation) | MATCH | Same name, same instrument text (First lien senior secured loan), same maturity (12/2029) and same rate base (SOFR). |
| 1829 | 3948 | EXACT_KEY | Blue Owl Credit Income Corp. | Cotiviti, Inc. | MATCH | Same name, same instrument text (First lien senior secured loan), same maturity (5/2031) and same rate base (SOFR). |
| 1835 | 3954 | EXACT_KEY | Blue Owl Credit Income Corp. | Himalaya Topco LLC (dba HealthEdge) | MATCH | Same name, same instrument text (First lien senior secured loan), same maturity (6/2032) and same rate base (SOFR).Cash spread S+ 3.00% now against S+ 2.75% before, PIK 2.25% in both: same base. |
| 1911 | 4033 | EXACT_KEY | Blue Owl Credit Income Corp. | Trucordia Insurance Holdings, LLC | MATCH | Same name, same instrument text (First lien senior secured loan), same maturity (6/2032) and same rate base (SOFR). |
| 1926 | 4047 | EXACT_KEY | Blue Owl Credit Income Corp. | Azurite Intermediate Holdings, Inc. (dba Alteryx, Inc.) | MATCH | Same name, same instrument text (First lien senior secured loan), same maturity (3/2031) and same rate base (SOFR). |
| 1936 | 4056 | EXACT_KEY | Blue Owl Credit Income Corp. | Catalis Intermediate, Inc. (fka GovBrands Intermediate, Inc.) | MATCH | Same name, same instrument text (First lien senior secured loan), same maturity (8/2027) and same rate base (SOFR).Spread S+ 5.25% now against S+ 5.50% before: same base. |
| 1996 | 4113 | EXACT_KEY | Blue Owl Credit Income Corp. | Themis Solutions Inc. (dba Clio) | MATCH | Same name, same instrument text (First lien senior secured loan), same maturity (10/2032) and same rate base (SOFR). |
