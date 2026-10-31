# Blocking recall decisions

Counterparts in this file were identified by an AI assistant (Claude Code) from raw filing text, using the rules below, not by hand. They were decided before --finalize and not read from any blocker output.

## Rules

- Each of the 30 drawn holdings (`docs/blocking_recall_worksheet.md`) was looked up with `python -m pipeline.blocking_recall --search TEXT --for HOLDING_ID` and the raw columns it prints. No blocking key, candidate pair, score, band or normalized column was queried or read, and block.py and match.py were not run.
- A counterpart must match on all four: the same borrower; the same kind of instrument (revolver, delayed draw or term loan, read from the printed instrument text, with the lien class matching); the same rate base and spread (SF, SOFR and S are one base, P and Prime are one, SONIA and EURIBOR stay distinct); and the same maturity month and year.
- Principal, industry and cost are not evidence.
- Before NONE, at least three search texts were tried: the first distinctive word, the first two words, and a spelling variant without suffixes. The terms are in the table.
- If the borrower matches but the instrument kind, rate or maturity cannot be confirmed from the printed text, the pair is not recorded and is logged AMBIGUOUS with the reason.
- If the same loan exists at both other BDCs, the one with the lower holding id is recorded.
- How the rules were applied to instrument kind in the first pass: ADS prints the kind (Term Loan, Delayed Draw, Revolver). ORCIC prints revolving and delayed draw loans with those words, so a plain first lien senior secured loan is read as a term loan. HPS prints First Lien Debt for every kind (its revolver and term rows carry the same text), so its kind cannot be read, and any pair that has an HPS holding on either side is AMBIGUOUS at best. This is strict on purpose, and it is why only pairs between ADS and ORCIC can be recorded.

## Revision (second pass, decided before the blocking outcome of these seven was looked at)

Reason: the first pass recorded 2 pairs (both found by blocking). Seven holdings were AMBIGUOUS only because HPS prints no instrument kind, so the strict rule excluded every pair with an HPS holding on either side. The revision was decided from raw attributes through `--search` only, before `--finalize` was run again and without reading `blocking_keys`, `candidate_pairs`, scores, bands or normalized columns. It applies to the seven AMBIGUOUS holdings only. No NONE and no FOUND decision was reopened.

- **Tier A (strict, unchanged):** both sides print the instrument kind and all four match (borrower, kind, rate base and spread, maturity month and year). The 2 pairs already recorded (100 with 1856, 815 with 2038) stay.
- **Tier B (new):** exactly one side is HPS, which prints no instrument kind. The pair is accepted if every printed attribute that can be compared is equal: the same borrower (ignoring suffixes and dba names), the same lien class, the same rate base, the same total spread (a PIK split inside the spread does not matter) and the same maturity month and year. If the kind is readable on the non-HPS side, nothing further is needed. If the HPS side prints no rate, or any compared attribute differs, the pair stays AMBIGUOUS and is not recorded. A readable-kind row at the other BDC with a different kind from the one being matched is not a counterpart.
- **Several rows qualify:** the lowest holding id is recorded and the log says several qualified.
- **Rate base note:** HPS prints SN for SONIA (its own footnote text says "SONIA" or "SN"), SF for SOFR and C for CORRA.

| Holding | Name | Old decision | New decision | Counterpart | Printed attributes that matched or did not |
|---|---|---|---|---|---|
| 276 | Orthrus Ltd (ADS) | AMBIGUOUS | FOUND (Tier B) | 1046 | ADS Delayed Draw, SONIA+625, 12/05/2031. HPS 1046 (First Lien Debt): SN + 6.25% (incl 2.75% PIK), 12/5/2031: borrower, lien class, base (SN is SONIA), total spread 6.25% and month all match. The other HPS Orthrus rows did not qualify: 1047 is E (EURIBOR), 1048 and 1050 are SF (SOFR), 1049 prints no rate. |
| 503 | Cambrex Corp. (ADS) | AMBIGUOUS | FOUND (Tier B), several qualified | 1262 | ADS Revolver, S+475, 03/05/2032. HPS 1262, 1263 and 1264 (First Lien Debt): SF + 4.75%, 3/8/2032, all equal on every comparable attribute, so the lowest id is recorded. ORCIC 1753 (first lien senior secured loan, a term loan) has a different readable kind from the revolver and is not a counterpart. |
| 1091 | Aryeh Bidco Investment Ltd (HPS) | AMBIGUOUS | FOUND (Tier B), several qualified | 342 | HPS First Lien Debt, C + 5.00%, 1/14/2033. ADS 342 (Term Loan), 343 (Delayed Draw) and 344 (Revolver), all C+500 and 01/14/2033, and ORCIC 1784 (first lien senior secured delayed draw term loan, C+ 5.00%, 1/2033, printed as dentalcorp Health Services Ltd. fka Aryeh Bidco Investment Ltd.) all equal the HPS attributes. The lowest id is recorded; the HPS row does not say which kind it is. |
| 1223 | Integrity Marketing Acquisition LLC (HPS) | AMBIGUOUS | AMBIGUOUS (not recorded) | | HPS prints no rate (First Lien Debt, 8/25/2028), so the rate base and spread cannot be compared with ORCIC 1898 (S+ 5.00%, 8/2028). |
| 1258 | Bamboo US BidCo LLC (HPS) | AMBIGUOUS | FOUND (Tier B) | 1748 | HPS First Lien Debt, SF + 5.25%, 9/30/2030. ORCIC 1748 (first lien senior secured loan, readable as a term loan): S+ 5.25%, 9/2030, all match. ORCIC 1749 is E+ (EURIBOR) and 1750 matures 10/2029, so neither qualifies. |
| 1468 | Storable Inc (HPS) | AMBIGUOUS | FOUND (Tier B) | 1993 | HPS First Lien Debt, SF + 3.25%, 4/16/2031. ORCIC 1993 (Storable, Inc., first lien senior secured loan): S+ 3.25%, 4/2031, all match. ORCIC 1994 (Storable Intermediate Holdings, LLC, S+ 6.00%, 4/2032) differs. |
| 1688 | ABB/Con-cise Optical Group LLC (ORCIC) | AMBIGUOUS | FOUND (Tier B) | 1064 | ORCIC first lien senior secured loan, S+ 7.50%, 2/2028. HPS 1064 (ABB/CON-CISE Optical Group LLC, First Lien Debt): SF + 7.50%, 2/23/2028: borrower, lien class, base, spread and month match. |

Revised result: 8 FOUND (2 Tier A, 6 Tier B), 1 AMBIGUOUS (1223) and 21 NONE.

## First pass (kept as decided)

First pass result: 2 FOUND, 7 AMBIGUOUS, 21 NONE (30 holdings)

| Holding | Name | BDC | Decision | Counterpart | Search terms tried | Printed attributes that matched or did not |
|---|---|---|---|---|---|---|
| 100 | Saber Parent Holdings Corp | Apollo Debt Solutions BDC | FOUND | 1856 | saber; saber parent; sabre | ADS: First Lien Secured Debt - Revolver, P+350, 12/16/2032. ORCIC 1856 (Saber Parent Holdings Corp. dba Service Logic): first lien senior secured revolving loan, P+ 3.50%, 12/2032: borrower, revolver, Prime base and 3.50, Dec 2032 all match. HPS 874 to 876 (First Lien Debt, 12/16/2032, 876 at P + 3.50%) were not usable: HPS prints no instrument kind, so a revolver cannot be confirmed. |
| 262 | Tulip Bidco Limited | Apollo Debt Solutions BDC | NONE |  | tulip; tulip bidco; tulip limited | Nothing listed at HPS or ORCIC by any term. |
| 276 | Orthrus Ltd | Apollo Debt Solutions BDC | AMBIGUOUS |  | orthrus; orthrus ltd; orthrus | ADS: Delayed Draw, SONIA+625, 12/05/2031. HPS 1046 to 1050 (Orthrus Ltd, First Lien Debt, 12/5/2031): 1046 is SN + 6.25% (incl 2.75% PIK), the same base and spread, but HPS prints no instrument kind, so delayed draw cannot be confirmed; five Orthrus rows at HPS with SN, E and SF bases. Not recorded. |
| 283 | Paisley Bidco Limited | Apollo Debt Solutions BDC | NONE |  | paisley; paisley bidco; paisley limited | Nothing listed at HPS or ORCIC by any term. |
| 319 | Heartbeat BidCo GmbH | Apollo Debt Solutions BDC | NONE |  | heartbeat; heartbeat bidco; heartbeat gmbh | Nothing listed at HPS or ORCIC by any term. |
| 357 | OMH-Healthedge Holdings, Inc. | Apollo Debt Solutions BDC | NONE |  | omh; omh healthedge; healthedge | ADS: Term Loan, S+425, 04/01/2030. Only 'healthedge' listed ORCIC 1835 and 1836 (Himalaya Topco LLC dba HealthEdge): different printed borrower, maturity 6/2032 not 2030, spread S+3.00% plus 2.25% PIK (term) and S+5.00% (revolving). |
| 382 | Acentra Holdings, LLC | Apollo Debt Solutions BDC | NONE |  | acentra; acentra holdings; acentra health | Nothing listed at HPS or ORCIC by any term. |
| 503 | Cambrex Corp. | Apollo Debt Solutions BDC | AMBIGUOUS |  | cambrex; cambrex corp; cambrex corporation | ADS: Revolver, S+475, 03/05/2032. HPS 1262 to 1264 (Cambrex Corporation, First Lien Debt, SF + 4.75%, 3/8/2032): borrower, base, spread and month match but HPS prints no instrument kind and has three rows, so a revolver cannot be confirmed. ORCIC 1753 (first lien senior secured loan, S+ 4.75%, 3/2032) is a term loan, not a revolver. Not recorded. |
| 642 | Jensen Hughes, Inc | Apollo Debt Solutions BDC | NONE |  | jensen; jensen hughes; jensenhughes | Nothing listed at HPS or ORCIC by any term. |
| 693 | Endor Purchaser, Inc. | Apollo Debt Solutions BDC | NONE |  | endor; endor purchaser; endor | Nothing listed at HPS or ORCIC by any term. |
| 724 | Kaseya Inc | Apollo Debt Solutions BDC | NONE |  | kaseya; kaseya inc; kaseya | ADS: Revolver, S+325, 03/20/2030. HPS 1410 (First Lien Debt, SF + 3.25%) matures 3/22/2032; ORCIC 1652 (first lien loan, S+ 3.25%) matures 3/2032; ORCIC 1653 is second lien, S+ 5.00%, 3/2033. No instrument with a 2030 maturity. |
| 815 | CCI Buyer, Inc. | Apollo Debt Solutions BDC | FOUND | 2038 | cci; cci buyer; consumer cellular | ADS: First Lien Secured Debt - Term Loan, S+500, 05/31/2032. ORCIC 2038 (CCI BUYER, INC. dba Consumer Cellular): first lien senior secured loan (ORCIC names revolving and delayed draw loans separately, so a plain loan is a term loan), S+ 5.00%, 5/2032: all four match. HPS 1511 and 1512 (First Lien Debt, 5/13/2032, 1512 at SF + 5.00%) were not usable: no instrument kind printed. |
| 824 | Fastener Distribution Holdings, LLC | HPS Corporate Lending Fund | NONE |  | fastener; fastener distribution; fastener holdings | Nothing listed at ADS or ORCIC by any term. |
| 1091 | Aryeh Bidco Investment Ltd | HPS Corporate Lending Fund | AMBIGUOUS |  | aryeh; aryeh bidco; aryeh | HPS: First Lien Debt, C + 5.00%, 1/14/2033. ADS 342 (Term Loan), 343 (Delayed Draw), 344 (Revolver), all C+500 and 01/14/2033; ORCIC 1784 (dentalcorp Health Services Ltd. fka Aryeh Bidco Investment Ltd., delayed draw term loan, C+ 5.00%, 1/2033). Borrower, base and maturity match but HPS prints no instrument kind, so which of the four it pairs with cannot be confirmed. Not recorded. |
| 1095 | Aspen Dental Management Inc. (ADMI Corp) | HPS Corporate Lending Fund | NONE |  | aspen; aspen dental; admi | Nothing listed at ADS or ORCIC by any term. |
| 1182 | HB AcquisitionCo Pty Ltd | HPS Corporate Lending Fund | NONE |  | hb acquisitionco; hb acquisition; hb | Nothing listed at ADS or ORCIC by any term. |
| 1196 | Marcone Group Inc | HPS Corporate Lending Fund | NONE |  | marcone; marcone group; marcone | Nothing listed at ADS or ORCIC by any term. |
| 1212 | CRC Insurance Group LLC | HPS Corporate Lending Fund | NONE |  | crc; crc insurance; crc insurance group | Nothing listed at ADS or ORCIC by any term. |
| 1223 | Integrity Marketing Acquisition LLC | HPS Corporate Lending Fund | AMBIGUOUS |  | integrity; integrity marketing; integrity marketing acquisition | HPS: First Lien Debt, 8/25/2028, no rate printed. ORCIC 1898 (Integrity Marketing Acquisition, LLC, first lien senior secured loan, S+ 5.00%, 8/2028): borrower and maturity match, but HPS prints no rate and no instrument kind. Not recorded. |
| 1258 | Bamboo US BidCo LLC | HPS Corporate Lending Fund | AMBIGUOUS |  | bamboo; bamboo us; bamboo bidco | HPS: First Lien Debt, SF + 5.25%, 9/30/2030. ORCIC 1748 (first lien senior secured loan, S+ 5.25%, 9/2030): borrower, base, spread and month match, but HPS prints no instrument kind. ORCIC 1749 is a EUR term loan (E+) and 1750 a revolving loan (10/2029). Not recorded. |
| 1297 | LOCI Bidco Limited | HPS Corporate Lending Fund | NONE |  | loci; loci bidco; loci limited | Only 'loci' listed ORCIC 1667 (Velocity HoldCo III Inc. dba VelocityEHS), a different borrower whose name contains the letters. |
| 1468 | Storable Inc | HPS Corporate Lending Fund | AMBIGUOUS |  | storable; storable inc; storable | HPS: First Lien Debt, SF + 3.25%, 4/16/2031. ORCIC 1993 (Storable, Inc., first lien senior secured loan, S+ 3.25%, 4/2031): borrower, base, spread and month match, but HPS prints no instrument kind. ORCIC 1994 (Storable Intermediate Holdings, LLC, S+ 6.00%, 4/2032) is a different row. Not recorded. |
| 1546 | Columbia Cent CLO 33 Ltd - Class E | HPS Corporate Lending Fund | NONE |  | columbia cent; columbia cent clo; cent clo 33 | Nothing listed at ADS or ORCIC by any term. |
| 1587 | Artemis Bidco Limited | HPS Corporate Lending Fund | NONE |  | artemis; artemis bidco; artemis limited | Nothing listed at ADS or ORCIC by any term. |
| 1688 | ABB/Con-cise Optical Group LLC | Blue Owl Credit Income Corp. | AMBIGUOUS |  | abb; con-cise; concise optical | ORCIC: first lien senior secured loan, S+ 7.50%, 2/2028. HPS 1064 (ABB/CON-CISE Optical Group LLC, First Lien Debt, SF + 7.50%, 2/23/2028): borrower, base, spread and month match, but HPS prints no instrument kind. Nothing at ADS. Not recorded. |
| 1701 | Dresser Utility Solutions, LLC | Blue Owl Credit Income Corp. | NONE |  | dresser; dresser utility; dresser solutions | Nothing listed at ADS or HPS by any term. |
| 1706 | Blackhawk Network Holdings, Inc. | Blue Owl Credit Income Corp. | NONE |  | blackhawk; blackhawk network; blackhawk | Nothing listed at ADS or HPS by any term. |
| 1738 | Hissho Parent, LLC | Blue Owl Credit Income Corp. | NONE |  | hissho; hissho parent; hissho | Nothing listed at ADS or HPS by any term. |
| 2011 | MHE Intermediate Holdings, LLC (dba OnPoint Group) | Blue Owl Credit Income Corp. | NONE |  | mhe; mhe intermediate; onpoint | Nothing listed at ADS or HPS by any term. |
| 2032 | Thevelia (US) LLC (dba Tricor) | Blue Owl Credit Income Corp. | NONE |  | thevelia; thevelia us; tricor | Only 'tricor' listed ADS 168 (TricorBraun Holdings, Inc., Term Loan, S+325, 03/03/2031): a different borrower and a different maturity (ORCIC 6/2029). |

## Diagnostic follow-up on four NONE rows (after the second finalize, nothing changed)

Holdings 262, 1095, 1297 and 1546 were looked at again, read only, to see whether a NONE could hide a blocking miss. This is a diagnostic. No decision, recorded pair, threshold or blocker setting was changed, and the recall figure was not recomputed. Method: the holding's own blocking keys, any other-BDC holding sharing one of those keys, any candidate pair involving it, and other-BDC raw rows with the same maturity month and rate base but a different name.

| Holding | Borrower (BDC, printed instrument) | Blocking behaviour | Reading |
|---|---|---|---|
| 262 | Tulip Bidco Limited (ADS, delayed draw, SONIA+373, 12/13/2027) | Block keys exist (type DELAYED_DRAW, name prefixes `tuli` and `tulip`). No holding of another BDC shares either key, and the holding is in no candidate pair. No HPS or ORCIC row has a SONIA base maturing in December 2027. | Legitimate NONE: the borrower is not in the other two schedules under this or any similar name. |
| 1095 | Aspen Dental Management Inc. (ADMI Corp) (HPS, SF + 5.75%, 12/23/2027) | Block keys exist (FIRST_LIEN, prefixes `aspe` and `aspen`). No other-BDC holding shares them, and there is no candidate pair. The only other-BDC row with a December 2027 maturity and a 5.75% spread is Gaylord Chemical Company, L.L.C. (ORCIC), a different borrower. | Legitimate NONE. |
| 1297 | LOCI Bidco Limited (HPS, SF + 5.23%, 5/19/2031) | Block keys exist (FIRST_LIEN, prefix `loci`). No other-BDC holding shares it, and there is no candidate pair. The only other-BDC row with a May 2031 maturity and a similar spread is Blitz 24-34 GmbH (ADS, S+525, 05/03/2031), a different borrower. | Legitimate NONE. |
| 1546 | Columbia Cent CLO 33 Ltd - Class E (HPS, structured finance, SF + 7.16%, 4/20/2037) | Normalized instrument type is OTHER, which block.py never treats as a candidate type (`NOT_CANDIDATE_TYPES` is OTHER and EQUITY), so it has no block keys at all. 36 holdings of the measured quarter are typed OTHER. | The NONE is correct, and it exposes a design limit rather than a defect: structured finance and other non loan positions are never blocked, so the blocking recall figure does not cover them. This is stated in the README limits. |

None of the four is suspicious. For 262, 1095 and 1297 the original search result (nothing listed by any of three terms) agrees with the blocking data: there is simply no counterpart in the other two schedules. For 1546 the miss is by design. No threshold was altered.
