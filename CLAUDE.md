# CLAUDE.md

Project: Cross-Lender Private Credit Valuation Monitor.
Source of truth: SPEC.md (scope, schema, evaluation, tests, schedule), CONTRACT.md (API shapes only), phase_wise.md (backend plan), frontend.md (UI plan). If plans disagree with SPEC.md or CONTRACT.md, those two win.

## Working rules
- Read the relevant doc sections before starting. Work only on the day or phase I name. Do not build ahead.
- Explain every file you create or change in a short summary so I can review the diff.
- I label the data. Never pre-label, suggest labels, or auto-fill labeled_pairs.
- Never run normalize.py, block.py or match.py after the matcher freeze.
- Never retune blocking after the freeze to improve pairs avoided or run times. Those are report-only.
- Never put a metric in the README that did not come from metric_results.
- Never include review-queue confirmations in any metric. evaluate.py must not read candidate_pairs.status.
- Do not write DECISIONS.md. I write it myself.
- I write the edge case tests (Holdings vs Holdco, digits in names, same-BDC collisions). Implement against them. Do not write tests that just mirror the implementation.
- Spot-check 10 displayed rows against the real SEC filing before calling a slice done.

## Technical rules
- Python 3.11 pipeline as a standalone CLI (python -m pipeline.<module>). Never imported by Node.
- Node 24, Express 5, plain JavaScript (ES modules) API. React 19 + Tailwind frontend. Postgres 16. Docker Compose v2.
- No ORM. Parameterized SQL only (psycopg in Python, pg in Node).
- All tunables live in pipeline/config.yaml. Secrets and MEASURED_PERIOD_END live in .env.
- Use NUMERIC in SQL and Decimal in Python for money and divergence. Never floats.
- fair_value_pct_par is NULL when principal is NULL or 0. Never divide by zero.
- source_url is carried through every table that holds a holding-level row. Never drop it in a join.
- Same-BDC pairs and cross-period pairs are never scored or clustered.
- Do not use the SEC companyfacts API. Parse Inline XBRL directly.
- SEC requests: User-Agent from env, max 5 req/s, backoff 1, 2, 4, 8.
- Pin all versions. Commit lockfiles. No latest Docker tags.

## Claims
- Non-claims: not Apollo's internal valuation, not ICE ID reverse engineering, not market-wide, no cross-quarter claim.
- Never imply Splink results unless built. Never claim Java or Spring Boot experience.

## Frontend rules
- Build against the real API from Day 7. No invented sample numbers.
- web/src/types.js (JSDoc typedefs) mirrors CONTRACT.md exactly. Change the contract first if it changes.
- UI strings use plain sentences and simple bullets. Avoid dashes and em-dashes. Write ranges as "to".
- Null from the API renders "Not yet measured".