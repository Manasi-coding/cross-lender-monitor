# Demo script

Demo recording is out of scope for now, because deployment is the next stage. This file is kept as the script to use when a recording is made, and its numbers were checked against the live stack on 2026-10-31.

About 6 minutes. Record the browser at http://localhost:8080 after `docker compose up`. Say only what the screen shows. Do not claim anything the README does not.

## Before recording
- Run `docker compose up` and wait until all services are healthy (`docker compose ps`).
- Open the app at a window width of about 1280 pixels, light theme.
- Have README.md and DECISIONS.md open in another tab.

## Interactive behavior (see DECISIONS.md for the full note)
Every number on screen still comes straight from the API, read exactly as CONTRACT.md defines it. Loading skeletons and a Retry button on failure, a save-confirmed toast on Review, and a count-up on stat cards that always lands on the exact API figure. None of it polls, ticks, or implies the data itself is live. The visible page silently refetches on window focus, so a count that changed elsewhere (for example a Review decision made in another tab) catches up without a manual reload.

## Steps
1. Overview (/). Say the question: do two lenders agree on what the same private loan is worth? Point to the stat cards (Facilities, Need review, Flagged exposure, Agreement) and note they count up to their value on load (the final number is exactly what the API returned, nothing simulated). Point to the Valuation differences donut and the Biggest differences list. Click a segment of the Valuation differences bar (for example Flagged) and show it lands on the Facilities page pre-filtered to that status. Point to the Data coverage card for lender, quarter and facility counts.
2. Facilities (/facilities, nav label "Triage"). The page lists all facilities by exposure; point to the four status tiles (Facilities, Agreement, Review, Flagged) and show that clicking one applies that filter, same as the filter pills below the charts. Point to one row in the Facility directory: borrower, instrument type, lender count, exposure, difference in points, status dot. There is no search box or sort control on this page; the table is always sorted by exposure. ERC has the largest divergence (64.15 points) and 22.07% of flagged exposure; say that its DIFFERENT_TRANCHE hand check is provisional (DECISIONS.md), so it may inflate flagged exposure.
3. Open a row's "View" link (Comparison; today the top flagged card is Severin Acquisition). Show the "Current reported value" card (one bar per lender, zoomed axis) with the point spread and, when present, the "Why the values may differ" signal line. Show the "Loan details" card (loan type, interest rate, maturity, reporting period) and the "Lender reports" card (each lender's value and loan amount, with the prior quarter's value shown inline when linked). Note there is no sortable table and no expandable evidence dossier on this page; the full dossier fields (cost % of par, FV % of cost, floor, PIK, non-accrual) are still in the API (E5) but are not shown here.
4. Borrowers (/borrowers). Use the header search box (top of every page) to search for a borrower; note the search term lands in the URL (`?search=`) and this page reads it from there, since Borrowers has no search box of its own. Click a status tile or filter pill, open a borrower, then open a facility from it.
5. Review queue (/review). Explain the difference between a "Possible match" card and a "Group issue" card. The page shows one case at a time with Previous and Next controls, not every card at once. Do not click a decision button while recording unless you mean to change the data. If you do act on a pair, show the card fade out only after the "Decision saved" toast appears, and that the sidebar's Review count and the Overview page update to match. On a Group issue card, show that clicking "Same" on a record also fades it out and logs a decision, even though it makes no API call (the pair is already matched; there is nothing to write).
6. Decisions (/decisions). Show the decision log this browser has recorded this session: Confirmed, Rejected and "Left as is" (the Group issue "Same" action) counts and a table of each decision. Say plainly that this is a session-only, in-browser log, not a database table: it starts empty on every reload and there is no server endpoint that lists past decisions.
7. Metrics (/metrics). Start with the compact dashboard: Match quality, Found matches, Search found and Labelled cases tiles, plus the Matching performance and "Where the system finds matches" charts. Click "Show full statistical detail" to reveal the full breakdown: AUTO only precision shown three ways with its interval and a low-to-high range bar, the REVIEW band as "1 of 5" counts, the out of time check as its own separate section, evidence signals, the unexplained share (8 of 12), field coverage and the divergence sensitivity table.
8. Filings (/filings). Show the Filings table, the Filings coverage matrix (lender by quarter) and the Latest filings list, then click a row to show its detail card and the SEC filing link. The three 2026-03-31 filings carry the tag "Outside measured quarter".
9. In the README, show the Evaluation section, the sensitivity note and the limits (282 of 283 AUTO pairs have equal normalized names; blocking recall is 6 of 8 on 8 recorded pairs, 75.0% with a 95% Wilson interval of 40.9% to 92.9%, split Tier A 2 of 2 and Tier B 4 of 6, and all of it identified by an AI assistant, not by hand, so say it is weak evidence). Open DECISIONS.md section 24 and read the provenance lines as they are written.

## Things not to say
- That anything explains a gap, or that the project reproduces Apollo's valuation.
- A precision that includes review queue confirmations.
- That ERC is confirmed as the same tranche, or that its exposure is reliable.
- That blocking recall is strong evidence (n is 8), or that the blocking recall and history link checks were done by hand: they were done by an AI assistant.
- That the Decisions page is a database record, or that a Group issue "Same" sends a write to the server.
