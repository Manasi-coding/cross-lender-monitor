# Demo script

About 6 minutes. Record the browser at http://localhost:8080 after `docker compose up`. Say only what the screen shows. Do not claim anything the README does not.

## Before recording
- Run `docker compose up` and wait until all services are healthy (`docker compose ps`).
- Open the app at a window width of about 1280 pixels, light theme.
- Have README.md and DECISIONS.md open in another tab.

## Interactive behavior (added, see DECISIONS.md for the full note)
Every number on screen still comes straight from the API, read exactly as CONTRACT.md defines it. What changed is how the page responds to being used: loading skeletons and a Retry button on failure, URL-synced filters on Borrowers and Triage, sortable and expandable evidence rows on Comparison, a save-confirmed toast on Review, and a count-up on the Overview stat cards that always lands on the exact API figure. None of it polls, ticks, or implies the data itself is live.

## Steps
1. Overview (/). Say the question: do two lenders agree on what the same private loan is worth? Point to 3 BDCs, 93 facilities, pending reviews and the divergence card (72 agreement, 9 mild, 12 flagged). Point to the line "Ranking key, not an estimate of loss." Note the stat cards count up to their value on load (the final number is exactly what the API returned, nothing simulated). Click a segment of the Valuation differences bar (for example Flagged) and show it lands on Triage pre-filtered to that status.
2. Triage (/facilities). The default view is all facilities, sorted by borrower. Click the Flagged chip and switch Sort to Exposure; point out the URL now reads `?flag=FLAGGED&sort=exposure`, so reload or Back restores the same view. Point to one card: flag with points, exposure, signal count, persistence tag. Type a borrower name in the search box and show it also lands in the URL. ERC has the largest divergence (64.15 points) and 22.07% of flagged exposure; say that its DIFFERENT_TRANCHE hand check is provisional (DECISIONS.md), so it may inflate flagged exposure.
3. Open the top card (Comparison; today it is Severin Acquisition). Show the banner with the point spread, the lender table and the Source links. Click a column header (for example FV % of par) to sort the lender rows, then click a row's chevron to expand its evidence dossier (cost % of par, FV % of cost, floor, PIK, maturity, non-accrual, each already returned by E5). Click one Source link and show the filing opens. This is how every number is sourced.
4. Open a facility that has signals (select All on Triage and pick one with a signal count above 0, for example Auctane, a mild facility with one signal, Cost basis gap). Show the Evidence panel: the signal chip, a dossier row expanded showing a column marked "differs", a "Not disclosed" cell, the dot plot and the History strip. Say "signals present, not causes" and "two quarters are not a trend".
5. Borrowers (/borrowers). Search for a borrower (note the debounce and that the search term lands in the URL), open it, then open a facility from it.
6. Review queue (/review). Explain what a cluster card is. Do not click Confirm or Reject while recording unless you mean to change the data. The 19 cluster cards come first; scroll past them to the 5 pair cards. Click Skip on a pair card to show it hides locally. If you do act on a pair, show the card fade out only after the "Decision saved" toast appears, and that the sidebar's Review count and the Overview page update to match.
7. Metrics (/metrics). Start with the headline: AUTO only precision shown three ways with its interval, now with a low-to-high range bar under each line. Say how UNSURE is counted. Show the REVIEW band as "1 of 5" counts. Show that the out of time check is a separate section. Show the evidence signals, the unexplained share (8 of 12), field coverage and the divergence sensitivity.
8. Filings (/filings). Show the SEC filing links. The three 2026-03-31 filings carry the tag "Outside measured quarter".
9. In the README, show the Evaluation section, the sensitivity note and the limits (282 of 283 AUTO pairs have equal normalized names; blocking recall is not yet measured). Open DECISIONS.md section 24 and read the provenance lines as they are written.
10. Switch away from the tab and back (or minimize and restore the window). Point out the visible page silently refetches on focus, so a count that changed elsewhere (for example a Review decision made in another tab) catches up without a manual reload.

## Things not to say
- That anything explains a gap, or that the project reproduces Apollo's valuation.
- A precision that includes review queue confirmations.
- That ERC is confirmed as the same tranche, or that its exposure is reliable.
- That blocking recall was measured, until you have finished the hand check and run `--finalize`.
