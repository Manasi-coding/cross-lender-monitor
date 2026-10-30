# v2 Addendum: Triage, Evidence and History

Project: **Cross-Lender Private Credit Valuation Monitor**.
Status: draft for your review. Nothing here is merged into `SPEC.md`, `CONTRACT.md`, `phase_wise.md` or `frontend.md` yet. Once merged, those files win and this file is only the change list.

Reading note: you wrote "text set". I read it as **test set** (section 7). If you meant a text corpus, tell me, because the project uses no text corpus and no LLM.

Estimates in this file are my own planning numbers, not measurements. Claude Code speed and filing quirks will move them.

---

## 0. Summary

| # | Feature | What the analyst gets | Status | Build days |
|---|---|---|---|---|
| F1 | Exposure triage | A queue of flagged facilities ranked by dollars at stake, not just points | Committed | about 0.75 |
| F2 | Evidence dossier | For each facility, the filing facts that sit next to the gap: cost basis, spread, floor, PIK, maturity, non-accrual, exact source | Committed | about 1.5 |
| F3 | History and persistence | Whether the gap was already there last quarter: widened, narrowed, closed or stable | **Gated** | about 2 |

Total: F1 and F2 add about 2.25 build days and the cuts in section 8 return about 0.5, so the net is about **+1.75 days**. That fits the 12-day plan only by spending the whole Day 12 buffer. Plan for **13 to 14 build days**. With F3 it is **15 to 16**.

What does not change: the matcher, the evaluation design, the freeze, the 26 existing tests, the "no LLM" rule. F1 and F2 sit outside the matcher hash.

---

## 1. Why this exists (how we got to this conclusion)

**Starting point.** After Day 3 the project was strong on data engineering and on a measured, non-circular matcher evaluation. A reviewer's critique said the weak point is the "so what": the system flags a divergence and then stops.

**The question we asked.** After the system flags a facility, what does an investment professional do? Three things, in order:
1. Decide whether it is worth their time. That is a question of size.
2. Look for anything in the filings that sits next to the gap. That is a question of evidence.
3. Check whether it is new or old. That is a question of history.

Each feature answers exactly one of those questions. Nothing is added that does not.

**What we considered and rejected.**

| Idea | Why not |
|---|---|
| ML anomaly detector or mark predictor | One quarter and no ground truth, so it cannot be measured, and unmeasured ML is what an interviewer picks apart |
| LLM-written explanations | Breaks the no-LLM rule and cannot be checked against a source |
| Composite risk score with weights | The weights would be arbitrary, and you would have to defend them |
| FX conversion of non-USD principal | The filings carry no rate, so it needs a dated outside source and its own evaluation |
| Running the matcher on the prior quarter | A new measured step with its own labeling. F3 avoids it (section 2.3) |
| Learned scorer vs rule baseline | Possible on Day 12 only. Not part of this addendum |

**What is data-backed and what is not.**
- Data-backed: Days 1 and 2 found the signals really are in the filings. 22 ADS rows carry a non-accrual footnote, and Vita Global shows cost above par with a deep markdown. So the dossier has material to show.
- Not backed: no analyst has been asked whether this layout helps. The README should say "designed around the analyst's decision, not validated with analysts". Do not claim Apollo or anyone works this way.

**The honest limit.** Public filings will explain only part of any gap. Blocking already forces maturity within 3 months and spread within 50 bps, so large attribute differences are rare inside matched facilities. The result worth reporting is how often a signal is present, and how many flagged gaps have none.

---

## 2. Feature definitions

### 2.1 F1 Exposure triage

```
exposure_usd = (divergence_pts / 100) * MIN(principal over included holdings)
```

- Included holdings already have a non-null, nonzero, USD principal, because `fair_value_pct_par` is non-null only then. No new guard is needed.
- MIN, not SUM or MAX, because lenders hold different slices of a syndicated loan. MIN is the conservative size: the gap in points applied to the smallest position being compared.
- It is a **ranking key, not an estimate of loss.** Say this on the page.
- Rank: `exposure_usd` descending, then `divergence_pts` descending, then `facility_id` ascending. Deterministic.
- The flag (AGREEMENT, MILD, FLAGGED) and the points stay visible. Dollars never replace them.
- No weights, no new config values.

### 2.2 F2 Evidence dossier

**Per lender row, from data already parsed:** cost, cost as % of par, fair value as % of cost, total spread, PIK bps, floor bps, maturity date, non-accrual yes or no, source link.

**Signals** (computed once in `compare.py`, stored as codes):

| Code | Fires when | Default |
|---|---|---|
| `NON_ACCRUAL` | any included holding is non-accrual | |
| `PIK_DIFFERS` | `pik_bps` differs across included holdings | any difference |
| `FLOOR_DIFFERS` | floor differs by at least X bps | 25 |
| `SPREAD_DIFFERS` | total spread differs by at least X bps | 25 |
| `MATURITY_DIFFERS` | maturity dates differ by at least X days | 31 |
| `COST_BASIS_GAP` | cost % of par differs by at least `divergence.mild_pts` | 1.0 |

Why these defaults: 25 bps is half the 50 bps blocking window, 31 days is one month because ORCIC maturity is stored as a month end, and the cost gap reuses the existing 1.0 point cutoff. They go in `config.yaml` under `evidence:`. They are **not tuned** to make the result look better.

**Wording.** Always "signals present", never "explained by" or "caused by".

**Reported results (descriptive only, no causal claim):**
1. **Signal lift table.** For each signal, the share of FLAGGED facilities that carry it against the share of AGREEMENT facilities that carry it, with both n. This shows whether a signal actually separates flagged from agreeing facilities.
2. **Unexplained share.** FLAGGED facilities with no signal. These are the ones an analyst has to investigate by hand.
3. **Field coverage.** For each field and each BDC, the share of compared holdings where it was parsed. A missing field shows "Not disclosed". It is never filled in.

### 2.3 F3 History and persistence (gated)

**The key idea.** Do not run the matcher on the prior quarter. Cross-lender matches are decided once, on the measured quarter. Then, for each holding in a facility, find **the same holding in the same BDC one quarter earlier** and read its prior mark. The prior divergence is max minus min over those prior marks.

This matters because it adds no unmeasured cross-lender step. The only new unmeasured step is the **within-BDC link**, which is far easier and gets its own hand check.

**Within-BDC link rule** (`link_history.py`, deterministic, set-based SQL):
1. Key: `(bdc_cik, borrower_normalized, instrument_type_norm)`.
2. If exactly one current and one prior holding share the key, link them (`EXACT_KEY`).
3. If several share the key, link only where maturity dates are equal and the pairing is one to one (`EXACT_MATURITY`).
4. Anything ambiguous stays unlinked. Never guess. Log the count.
5. A prior holding links to at most one current holding.

**Persistence label**, using the existing cutoffs and no new constants. Let `delta = current divergence minus prior divergence`, and the dead band be `divergence.mild_pts` (1.0). Evaluate in this order:

| Label | Rule |
|---|---|
| `NO_PRIOR` | fewer than 2 facility holdings have a linked prior mark |
| `CLOSED` | current flag is AGREEMENT and prior flag was not |
| `WIDENED` | `delta >= dead band` |
| `NARROWED` | `delta <= minus dead band` |
| `STABLE` | otherwise |

**What you can say:** "this gap was also present last quarter" or "it was not". **What you cannot say:** "this is a trend". Two points are not a trend.

---

## 3. Data needed

| Need | Source | New? | Size |
|---|---|---|---|
| Current quarter, 3 BDCs | SEC EDGAR (already planned) | No | about 2,300 rows |
| Rate components (spread, floor, PIK) | Already inside `interest_rate_raw` and the HTML for HPS and ORCIC | No, but must be parsed into columns | none |
| Non-accrual flag | Footnote text, by a **per-filer pattern in config** (same method as the HPS unfunded pattern) | New pattern per filer | none |
| Prior quarter (F3 only) | Q1 2026 10-Q (period end 2026-03-31) for the same 3 BDCs | New, 3 filings | about 2,300 rows |

Notes:
- **I have not checked** that all three BDCs filed a 2026-03-31 10-Q with the same Schedule of Investments structure. Check on EDGAR before committing to F3, the way Day 1 checked the current quarter.
- The non-accrual pattern must be found per filer by reading footnotes, as `scout_footnotes.py` did for HPS. ADS has 22 known rows. HPS and ORCIC are unknown. Do not assume.
- **No outside data.** No FX, no price feeds, no credit agreements. Everything is from SEC filings, so every number keeps its `source_url`.
- Fixtures: one trimmed prior-quarter excerpt per filer (30 rows or fewer) added to the schema-drift tests.

---

## 4. How it maps into the existing documents

### 4.1 SPEC.md

| Section | Change |
|---|---|
| 2 Solution overview | Add one sentence of purpose: triage, evidence, history. Update non-claims: "history shows the prior-quarter marks of the same positions. It is not a trend and not a measured matching result." Measured set paragraph: block and match run on `MEASURED_PERIOD_END` only. A prior quarter is normalized as history. |
| 3.2 Screens | Facilities becomes Triage. Facility Comparison gains an Evidence panel, an exposure line and (F3) a History strip. |
| 3.3 Out of scope | Replace "cross-period facility linking and any cross-quarter claim" with "cross-lender matching on any quarter other than the measured one, and any trend claim". Within-BDC history links are in scope only if F3 passes its gate. |
| 3.4 Build priority | Add Triage after Facility Comparison. |
| 5 Architecture | `compare.py` gains steps 7 to 8 (below). New `link_history.py` runs before it (F3). |
| 6 Schema | Migration `007` (section 4.3). |
| 10.1 MVP | Add exposure ranking and the dossier. F3 goes under 10.3 stretch until its gate passes. |
| 11 Edge cases | Add: dossier field not disclosed; ambiguous within-BDC link; prior holding with null mark; prior quarter normalized but never blocked. |
| 12 | New 12.10: signals, lift table, field coverage (descriptive, report-only). New 12.11: link check (F3). Keep them separate from the matcher metrics. |
| 13 Tests | Add tests 27 to 38 (section 7). **Reword test 26**: a non-measured quarter produces no candidate pairs, no facilities and no label samples. |
| 14 Scaling | Move "cross-period facility linking" to "partly built". Cross-lender matching on other quarters stays future work. |
| 15 Defenses | Add: MIN principal, signal thresholds, history without re-matching. |
| 16 Resume | Add the bullet rules in section 10. |
| 18 Schedule | Replace with section 8. |
| 20.3 README | Add the evidence tables, the "signals present, not causes" line and the F3 limitation. |

### 4.2 CONTRACT.md (frozen, so every change is additive and needs a DECISIONS.md note)

**Convention added.** Row-level dossier fields (`costPctPar`, `floorBps`, `pikBps`, `maturityDate`, `nonAccrual`) use `null` to mean **not disclosed in the filing**. The UI renders "Not disclosed". The existing null rule ("Not yet measured") still covers every aggregate and every not-yet-computed field. This is a deliberate exception and must be written down.

**E1** adds `flaggedExposureUsd` (null until `facility_summary` has rows).

**E4** adds fields and two optional query parameters:
```
[ { ...existing,
    divergencePts, divergenceFlag, exposureUsd,
    signalCount,                  // length of signal_codes
    persistence } ]               // WIDENED|NARROWED|CLOSED|STABLE|NO_PRIOR, or null if F3 not built
?flag=AGREEMENT|MILD|FLAGGED      // optional filter
?sort=borrower|exposure           // default borrower, so today's order is unchanged
```
Invalid `flag` or `sort` returns 400. No new endpoint, so the index in both plans does not change.

**E5** adds:
```
exposureUsd,
signals: [ "NON_ACCRUAL" | "PIK_DIFFERS" | "FLOOR_DIFFERS"
         | "SPREAD_DIFFERS" | "MATURITY_DIFFERS" | "COST_BASIS_GAP" ],
rows[]: + { costPctPar, fvPctCost, floorBps, pikBps, maturityDate, nonAccrual },
history: null | { priorPeriodEnd, persistence, priorDivergencePts | null,
                  priorDivergenceFlag | null,
                  rows: [ { bdcName, priorFairValuePctPar | null } ] }
```
- `spreadBps` stays total spread (cash plus PIK). Cash spread is `spreadBps - pikBps`.
- `history` is null only when F3 is not built ("Not yet measured"). If F3 is built and the facility lacks two linked prior marks, `persistence` is `NO_PRIOR`.
- Decimal values use the same representation as `principal` in E5.

**E9** adds three fields:
```
evidenceLift:    [ { code, flaggedShare, flaggedN, agreementShare, agreementN } ] | null  // live
fieldCoverage:   [ { field, bdcName, parsedShare, n } ] | null                            // live
historyLinks:    { priorPeriodEnd, linkedShare, precision: Range | null } | null          // F3
```
`evidenceLift` and `fieldCoverage` are computed live from the curated tables, like `sensitivityTable`. `historyLinks.precision` comes from the hand check and is null until it is done. None of this reads `candidate_pairs.status`.

**Tests to update:** 12 and 22 (E5 shape), the E4 and E9 shape tests, and the null-rule test.

### 4.3 Schema: migration `007` (run on Day 4, before `compare.py` has written anything)

```sql
ALTER TABLE normalized_holdings
  ADD COLUMN non_accrual BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE facility_comparisons
  ADD COLUMN cost           NUMERIC,
  ADD COLUMN cost_pct_par   NUMERIC,   -- NULL unless fair_value_pct_par is non-null
  ADD COLUMN fv_pct_cost    NUMERIC,
  ADD COLUMN floor_bps      NUMERIC,
  ADD COLUMN pik_bps        NUMERIC,
  ADD COLUMN maturity_date  DATE,
  ADD COLUMN non_accrual    BOOLEAN;

ALTER TABLE facility_summary
  ADD COLUMN exposure_usd   NUMERIC NOT NULL CHECK (exposure_usd >= 0),
  ADD COLUMN signal_codes   TEXT[]  NOT NULL DEFAULT '{}';

CREATE INDEX idx_fs_exposure ON facility_summary (exposure_usd DESC, facility_id);
CREATE INDEX idx_fs_flag     ON facility_summary (divergence_flag);
```
The curated tables are empty until Day 7, so `NOT NULL` without a default is safe if this lands on Day 4.

**F3 only (migration `008`):**
```sql
CREATE TABLE holding_history_links (
  holding_id        INT PRIMARY KEY REFERENCES normalized_holdings(holding_id),
  prior_holding_id  INT NOT NULL UNIQUE REFERENCES normalized_holdings(holding_id),
  link_rule         TEXT NOT NULL            -- EXACT_KEY | EXACT_MATURITY
);
CREATE TABLE facility_history (
  facility_id            INT PRIMARY KEY REFERENCES canonical_facilities(facility_id),
  prior_period_end       DATE NOT NULL,
  prior_lender_count     INT  NOT NULL CHECK (prior_lender_count >= 2),
  prior_divergence_pts   NUMERIC NOT NULL,
  prior_divergence_flag  TEXT NOT NULL,
  persistence            TEXT NOT NULL       -- WIDENED|NARROWED|CLOSED|STABLE
);
CREATE TABLE history_link_checks (            -- hand check, like blocking_recall_checks
  check_id          SERIAL PRIMARY KEY,
  holding_id        INT NOT NULL REFERENCES normalized_holdings(holding_id),
  prior_holding_id  INT NOT NULL REFERENCES normalized_holdings(holding_id),
  label             TEXT NOT NULL,           -- MATCH | NO_MATCH | UNSURE
  labeled_by        TEXT NOT NULL,
  checked_at        TIMESTAMPTZ DEFAULT now()
);
```
Facilities without a row in `facility_history` are `NO_PRIOR`, derived by absence.

### 4.4 Where the logic runs

`compare.py` stays one deterministic full rebuild in one transaction. Added steps after divergence:
7. Fill the new `facility_comparisons` columns from `normalized_holdings` (set-based `INSERT ... SELECT`).
8. Compute `exposure_usd` and `signal_codes` per facility with SQL aggregates, using `evidence:` config values.
9. (F3) Read `holding_history_links`, write `facility_history` and its persistence label.

`link_history.py` (F3) is separate, deterministic and idempotent. It reads only `normalized_holdings`, never matcher output, and does a full rebuild of `holding_history_links`.

### 4.5 Interaction with the matcher freeze

This is the part that constrains the schedule.

- `normalize.py` is a hashed file. The **non-accrual detection and any rate-parsing fixes must land before the Day 8 freeze**, or you must unfreeze later.
- A prior quarter must be **ingested and normalized before the freeze**, because normalize refuses to run afterward. This is the one part of F3 that cannot wait.
- `block.py` and `match.py` must be restricted to `MEASURED_PERIOD_END` (config), so prior-quarter rows never become candidate pairs or label samples. Verify this on the first run, because otherwise `band_sizes` and `all_pairs` would be wrong.
- `compare.py`, `link_history.py` and the `evidence:` config should **not** be in `freeze.hashed_files`. Check `config.yaml` to confirm. If they are not, changing them after the freeze does not invalidate the held-out set.

### 4.6 phase_wise.md and frontend.md

- `phase_wise.md`: Phase 3 adapters also output rate components and a non-accrual flag. Phase 4 normalize carries `non_accrual`. Phase 6 compare adds steps 7 to 9. Phase 8 or 9 adds the dossier spot-check and (F3) the link check. The endpoint index copies E4 query parameters only if you list parameters there.
- `frontend.md`: section 4.4 (Facilities becomes Triage), 4.5 (Comparison), 4.7 (Metrics), section 7 components, section 8 cut order.

---

## 5. Frontend

**No new route and no new sidebar tab.** The sidebar stays at 6 tabs.

| Page | Change | Endpoint |
|---|---|---|
| **Facilities** (nav label becomes **Triage**, route stays `/facilities`) | Default view: `flag=FLAGGED`, `sort=exposure`. A toggle shows all facilities. Each card shows borrower, instrument, divergence flag with points, exposure in USD, signal count, and (F3) a persistence tag. | E4 |
| **Facility Comparison** | Banner adds the exposure line and the sentence "Ranking key, not an estimate of loss." New **Evidence panel**: the lender table extended with cost % of par, fair value % of cost, spread, floor, PIK, maturity, non-accrual. Cells that differ across lenders are marked, with text, not color alone. Signal chips with labels. (F3) **History strip**: prior to current dots per lender, plus the persistence label. | E5 |
| **Metrics** | New cards: signal lift table, unexplained share, field coverage per BDC. (F3) link accuracy with its interval. Each reads "Not yet measured" when null. | E9 |
| **Overview** | One extra card: flagged exposure. It is optional and goes first in the cut list. | E1 |
| Borrower Detail, Review Queue, Filings, Labeling | No change | |

**New shared components:** `ExposureTag`, `SignalChip`, `EvidenceTable`, `HistoryStrip` (inline SVG, same approach as `DotPlot`), `PersistenceTag`. No chart library.

**Rules carried over:** every number from a filing keeps its source link. Dossier nulls say "Not disclosed". Aggregates say "Not yet measured". Color is never the only signal. Build against the real API, never invented numbers.

**Cut order changes.** Landing page, Filings, Overview, then Borrower Detail polish. **Facilities (Triage) is no longer cuttable.**

---

## 6. Efficiency and latency

1. **Precompute everything.** Exposure, signals, dossier columns and history are written during `compare.py` and `link_history.py`. The API only reads, using indexed lookups. No aggregation happens per request.
2. **One round trip per page.** E5 returns the facility, the dossier and the history together. There is no N+1 and no follow-up call.
3. **One query per list.** E4 reads `facility_summary` joined to `canonical_borrowers`, ordered by the new index. About 100 to 200 facilities, so no pagination. **Trigger to revisit:** more than 1,000 facilities, then add keyset pagination.
4. **Set-based SQL.** Signals, exposure and the history link are `INSERT ... SELECT` with aggregates and one window function. No Python loop over rows or pairs. At roughly 2,300 rows per quarter this is well under a second.
5. **Cheap revalidation.** Data changes only when `compare.py` re-runs. Express already adds ETags to JSON, so send `Cache-Control: no-cache` and let repeat loads return 304. Turn on gzip for JSON in nginx.
6. **Frontend.** E1 is fetched once and shared. No chart library. Lists of a few hundred cards render without virtualization. **Trigger to revisit:** more than 500 rows.
7. **Budget (targets, not measurements).** Under 50 ms server time and under 100 KB per response for E4 and E5 on the compose stack. Measure on Day 10, write the machine spec beside it, and keep it report-only like §12.9. Do not quote it elsewhere.

---

## 7. Test set

### 7.1 Automated tests (added to SPEC §13)

| # | Test | Expected |
|---|---|---|
| 27 | Exposure formula | Two-lender and three-lender facilities, Decimal. MIN principal used. |
| 28 | Exposure ordering | Ties broken by points, then ascending `facility_id`. Two runs identical. |
| 29 | Signal boundaries | Each code at just below and at its threshold (24 and 25 bps, 30 and 31 days, 0.99 and 1.0 points). |
| 30 | Non-accrual pattern | One fixture per filer. Flag set only where the filing text matches. |
| 31 | E4 parameters | Valid `flag` and `sort` work. Invalid values return 400. Default order unchanged. |
| 32 | E5 additions | Shape matches CONTRACT.md. Dossier null renders as not disclosed. `spreadBps` is still total spread. |
| 33 | Link rule (F3) | Unique key links. Ambiguous stays unlinked. A prior holding links to at most one current holding. |
| 34 | Persistence (F3) | Deltas 0.99, 1.0, minus 1.0. `CLOSED` takes precedence. Fewer than 2 prior marks gives `NO_PRIOR`. |
| 35 | Prior quarter isolation (F3) | No candidate pair, facility or label sample from the prior quarter. |
| 36 | History null vs `NO_PRIOR` | F3 not built gives null. F3 built without prior marks gives `NO_PRIOR`. |
| 37 | Determinism | `compare.py` twice gives identical `exposure_usd`, `signal_codes` and `facility_history`. |
| 38 | E9 live fields | `evidenceLift` and `fieldCoverage` appear before `evaluate.py`. Flipping `candidate_pairs.status` changes nothing. |

Tests 33 to 36 exist only if F3 is built. The 26 existing tests stay, with 12, 22 and 26 updated as noted.

### 7.2 Hand-checked sets (and why)

| Set | Size | Why | Time | Reported as |
|---|---|---|---|---|
| **Dossier accuracy** | 30 holdings, 10 per BDC, random | The dossier is only useful if the parsed fields are right. Every field is compared with the SEC page. | about 1 h | Correct count per field, with n. No accuracy claim beyond what was checked. |
| **Exposure arithmetic** | 5 facilities | Confirms the formula end to end with a calculator. | about 15 min | Pass or fail |
| **Within-BDC link check (F3)** | 30 links, 10 per BDC | A wrong link makes fake history. Label with evidence not in the link key (industry, footnote text, the raw row), and use UNSURE when only the key agrees, the same discipline as §12.2. | about 45 min | Wilson interval, with the UNSURE range |

Why these and not a larger labeled set: the matcher is the part that needs a statistically defended evaluation, and it already has one. The new work is deterministic extraction and a simple join, so the right check is a correctness spot-check of fields and links, not a second 200-pair study.

---

## 8. Schedule and time

Day numbers are build days from `Week_Wise_Plan.md`, at about 6 to 8 focused hours.

| Day | Added work | Feature | Days added |
|---|---|---|---|
| 4 | Adapters also output spread, floor and PIK columns. Find the non-accrual footnote pattern per filer and put it in config. Migration `007`. | F2 | +0.25 |
| 5 | `normalize.py` carries `non_accrual`. **If Day 5 gates are met:** ingest and normalize the prior quarter. Restrict block and match to the measured period. | F3 prep | +0.5 (gated) |
| 7 | `compare.py` writes `exposure_usd`. E4 gets the new fields and parameters. | F1 | +0.25 |
| 9 | Signals and dossier columns in `compare.py`, E5 additions, tests 27 to 32, 37, 38. Dossier accuracy check. | F1, F2 | +0.75 |
| 10 | Triage view, Evidence panel, new Metrics cards. Drop Overview and Filings polish. Measure latency. | F1, F2 | +0.75 and **minus 0.5** |
| 11 | README and DECISIONS additions | docs | +0.25 |
| 12 and after | **F3 decision.** If it passes, `link_history.py`, `compare.py` step 9, E4, E5, E9, History strip, link check, tests 33 to 36 | F3 | +1.5 |

| Scope | Added | Net of cuts | Total build days |
|---|---|---|---|
| F1 and F2 | 2.25 | +1.75 | **13 to 14** |
| F1, F2 and F3 | 4.25 | +3.75 | **15 to 16** |

**What fits if you are behind:** F1 first (cheap, highest value), then the dossier fields without the lift table, then the lift table. F3 is the first thing to drop, and dropping it costs nothing already built except the Day 5 prior-quarter ingest.

---

## 9. Gates, risks and kill criteria

| Risk | Early signal | Response |
|---|---|---|
| Spread, floor or PIK parse badly for HPS or ORCIC | Field coverage below about 70% for a filer on Day 4 | Show "Not disclosed". Drop that signal from the lift table. Say so. Do not infer. |
| No non-accrual pattern found for a filer | Scout finds no footnote text | Mark `non_accrual` as not disclosed for that filer. Do not default to FALSE silently. |
| Prior quarter not available or structurally different | EDGAR check before Day 5 fails | Drop F3. Nothing else is affected. |
| Prior quarter ingest eats Day 5 | Day 5 gates not met by midday | Skip the ingest and decide F3 is out. |
| Most facilities have under 2 linked prior marks | Fewer than about half of facilities have history | Report the linked share. Either ship F3 as "limited" or drop it. |
| Time | Day 10 ends without the Triage view | Cut F2's lift table, keep F1 and the dossier columns |

**F3 gate, at the end of Day 9:** Q2 pipeline, E1 to E9 and the dossier are done, and the held-out evaluation is finished. If not, F3 goes to "future work" in the README.

---

## 10. Presenting it

**Why did you make this** (30 seconds):
"Private credit marks are estimates that nobody observes on a market, but several funds hold the same loan and each publishes its own mark. Nobody compares them, partly because the same borrower is named differently in each filing. I built a pipeline that matches the same loan across three public BDC filings, measured how accurate the matching is on a blind set, and then answers what an analyst would ask next: which gaps matter most, what in the filings sits next to them, and whether they were there last quarter."

**New likely questions**
- *Why rank by dollars?* Points ignore size. The ranking key is the gap applied to the smallest compared position. It is a sorting key, not a loss estimate, and the points stay visible.
- *Why not explain the gaps?* Public data cannot establish cause. I show which disclosed signals are present and report how many flagged gaps have none, which is the set an analyst must investigate.
- *Why no ML?* One quarter and no ground truth for marks, so a model could not be measured. The matcher is where classification matters and it is already evaluated.
- *How did you get history without re-matching?* Matches are decided once on the measured quarter. For each matched holding I link the same holding in the same BDC a quarter earlier, which is a much easier problem, and I hand-checked 30 of those links.
- *Is it a trend?* No. Two quarters show whether a gap persisted, widened or closed.

**Resume rules.** Quote a number only if it was measured: for example "of N flagged facilities, X had at least one disclosed signal and Y did not", with the per-field parse coverage. Never say the signals cause the gap. If F3 is not built, do not mention history.

---

## 11. Decisions to record in DECISIONS.md

1. Exposure uses MIN principal, and it is a ranking key, not a loss estimate.
2. The dossier null exception: row-level null means "not disclosed". Aggregates keep "Not yet measured".
3. Signal thresholds are defaults (25 bps, 31 days, 1.0 point), not tuned, and the lift table is descriptive.
4. Facilities becomes Triage, and is protected from cuts.
5. CONTRACT changes after the freeze are additive only: E1, E4 (fields and parameters), E5 and E9.
6. The prior quarter is history only. Block and match run on `MEASURED_PERIOD_END`.
7. Ambiguous within-BDC links stay unlinked.
8. Persistence uses the existing 1.0 point cutoff as its dead band.
9. F3 outcome at the Day 9 gate, and the reason.
10. Test 26 was reworded.
