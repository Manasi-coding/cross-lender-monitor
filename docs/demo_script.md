# Demo script

About 6 minutes. Record the browser at http://localhost:8080 after `docker compose up`. Say only what the screen shows. Do not claim anything the README does not.

## Before recording
- Run `docker compose up` and wait until all services are healthy (`docker compose ps`).
- Open the app at a window width of about 1280 pixels, light theme.
- Have README.md and DECISIONS.md open in another tab.

## Steps
1. Overview (/). Say the question: do two lenders agree on what the same private loan is worth? Point to 3 BDCs, 93 facilities, pending reviews and the divergence card (72 agreement, 9 mild, 12 flagged). Point to the line "Ranking key, not an estimate of loss."
2. Triage (/facilities). The default view is the flagged facilities ranked by exposure. Point to one card: flag with points, exposure, signal count, persistence tag. Type a borrower name in the search box. Click All, then Flagged again. ERC has the largest divergence (64.15 points) and 22.07% of flagged exposure; say that its DIFFERENT_TRANCHE hand check is provisional (DECISIONS.md), so it may inflate flagged exposure.
3. Open the top card (Comparison; today it is Severin Acquisition). Show the banner with the point spread, the lender table and the Source links. Click one Source link and show the filing opens. This is how every number is sourced.
4. Open a facility that has signals (select All on Triage and pick one with a signal count above 0, for example Auctane, a mild facility with one signal, Cost basis gap). Show the Evidence panel: the signal chip, the columns marked "differs", a "Not disclosed" cell, the dot plot and the History strip. Say "signals present, not causes" and "two quarters are not a trend".
5. Borrowers (/borrowers). Search for a borrower, open it, then open a facility from it.
6. Review queue (/review). Explain what a cluster card is. Do not click Confirm or Reject while recording unless you mean to change the data. The 19 cluster cards come first; scroll past them to the 5 pair cards. Click Skip on a pair card to show it hides locally.
7. Metrics (/metrics). Start with the headline: AUTO only precision shown three ways with its interval. Say how UNSURE is counted. Show the REVIEW band as "1 of 5" counts. Show that the out of time check is a separate section. Show the evidence signals, the unexplained share (8 of 12), field coverage and the divergence sensitivity.
8. Filings (/filings). Show the SEC filing links. The three 2026-03-31 filings carry the tag "Outside measured quarter".
9. In the README, show the Evaluation section, the sensitivity note and the limits (282 of 283 AUTO pairs have equal normalized names; blocking recall is not yet measured). Open DECISIONS.md section 24 and read the provenance lines as they are written.

## Things not to say
- That anything explains a gap, or that the project reproduces Apollo's valuation.
- A precision that includes review queue confirmations.
- That ERC is confirmed as the same tranche, or that its exposure is reliable.
- That blocking recall was measured, until you have finished the hand check and run `--finalize`.
