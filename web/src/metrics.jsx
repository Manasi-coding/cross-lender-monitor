import { useState } from "react";
import { getJson } from "./api.js";
import { BandTable, BarList, Card, CardLabel, Load, PageTitle, RangeBar, RangeStat, StatCard, ci, useFetch } from "./components.jsx";
import { NOT_YET, SIGNAL_TEXT, pct } from "./format.js";
// 4.7 Metrics. Every null field reads "Not yet measured" on its own. The held-out evaluation and the out-of-time report are shown
// separately and never pooled. No figure includes review-queue confirmations.
const FIELD_TEXT = {
  costPctPar: "Cost % of par",
  fvPctCost: "FV % of cost",
  spreadBps: "Spread",
  floorBps: "Floor",
  pikBps: "PIK",
  maturityDate: "Maturity",
};

export function MetricsPage() {
  const f = useFetch(() => getJson("/api/metrics"), []);
  return (
    <>
      <PageTitle>Metrics</PageTitle>
      <Load f={f}>{(m) => <Dashboard m={m} />}</Load>
    </>
  );
}

const headline = (range) => range?.unsureExcluded ?? null;

function averageFieldCoverage(rows) {
  if (!rows) return null;
  const sums = new Map();
  for (const r of rows) {
    const cur = sums.get(r.field) ?? { weighted: 0, n: 0 };
    cur.weighted += (r.parsedShare ?? 0) * r.n;
    cur.n += r.n;
    sums.set(r.field, cur);
  }
  return [...sums.entries()].map(([field, { weighted, n }]) => ({ field, share: n > 0 ? weighted / n : 0 }));
}

function Dashboard({ m }) {
  const [detail, setDetail] = useState(false);
  const precisionAuto = headline(m.precisionAutoOnly);
  const recallAuto = headline(m.recallAutoOnly);
  const precisionReview = headline(m.precisionReviewBand);
  const precisionLatest = headline(m.outOfTime?.precisionAutoOnly);
  const blocking = m.blockingRecall;
  const blockingFound = blocking ? Math.round(blocking.value * blocking.n) : null;

  // Tuning labels are diagnostic and excluded from evaluation counts.
  const heldOutN = m.heldOutCount;
  const latestN = m.outOfTime?.labeledCount ?? null;
  const labelledTotal = (heldOutN ?? 0) + (latestN ?? 0);

  const fieldAverages = averageFieldCoverage(m.fieldCoverage);

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard compact label="Match quality" value={precisionAuto ? pct(precisionAuto.value) : NOT_YET} tone="brand" />
        <StatCard compact label="Found matches" value={recallAuto ? pct(recallAuto.value) : NOT_YET} tone="brand" />
        <StatCard compact label="Search found" value={blocking ? pct(blocking.value) : NOT_YET} tone="review" />
        <StatCard compact label="Labelled cases" value={labelledTotal || NOT_YET} tone="neutral" />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <Card compact>
          <CardLabel>Matching performance</CardLabel>
          <BarList
            compact
            rows={[
              { label: "AUTO", value: precisionAuto ? Math.round(precisionAuto.value * 1000) / 10 : 0, color: "var(--color-chart-green)" },
              { label: "Review band", value: precisionReview ? Math.round(precisionReview.value * 1000) / 10 : 0, color: "var(--color-chart-yellow)" },
              { label: "Latest check", value: precisionLatest ? Math.round(precisionLatest.value * 1000) / 10 : 0, color: "var(--color-chart-green-dark)" },
            ]}
          />
        </Card>
        <Card compact>
          <CardLabel>Where the system finds matches</CardLabel>
          {blocking ? (
            <>
              <BarList
                compact
                rows={[
                  { label: "Found", value: blockingFound, color: "var(--color-chart-green)" },
                  { label: "Missed", value: blocking.n - blockingFound, color: "var(--color-chart-red)" },
                ]}
              />
              <p className="mt-2 text-xs" style={{ color: "var(--color-text-secondary)" }}>{blockingFound} found, {blocking.n - blockingFound} not found</p>
            </>
          ) : (
            <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>{NOT_YET}</p>
          )}
        </Card>
      </div>

      <Card compact>
        <CardLabel>Test results</CardLabel>
        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <p className="text-2xl font-bold" style={{ color: "var(--color-text)" }}>{heldOutN ?? NOT_YET}</p>
            <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-secondary)" }}>Held-out</p>
          </div>
          <div>
            <p className="text-2xl font-bold" style={{ color: "var(--color-text)" }}>{latestN ?? NOT_YET}</p>
            <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-secondary)" }}>Latest</p>
          </div>
        </div>
        <p className="mt-3 text-xs" style={{ color: "var(--color-text-secondary)" }}>Total: {labelledTotal || NOT_YET} tested cases</p>
      </Card>

      <div className="grid gap-3 lg:grid-cols-2">
        <Card compact>
          <CardLabel>What needs attention</CardLabel>
          {m.evidenceLift ? (
            <BarList
              compact
              rows={m.evidenceLift
                .filter((r) => r.flaggedShare !== null)
                .map((r) => ({ label: SIGNAL_TEXT[r.code] ?? r.code, value: Math.round(r.flaggedShare * 1000) / 10, color: "var(--color-chart-yellow)" }))}
            />
          ) : (
            <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>{NOT_YET}</p>
          )}
        </Card>
        <Card compact>
          <CardLabel>Information found</CardLabel>
          {fieldAverages ? (
            <BarList
              compact
              rows={fieldAverages.map((r) => ({ label: FIELD_TEXT[r.field] ?? r.field, value: Math.round(r.share * 1000) / 10, color: "var(--color-chart-green)" }))}
            />
          ) : (
            <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>{NOT_YET}</p>
          )}
          <p className="mt-2 text-xs" style={{ color: "var(--color-text-muted)" }}>How often each optional field was disclosed in the filings.</p>
        </Card>
      </div>

      <div className="text-center">
        <button type="button" className="btn-secondary" onClick={() => setDetail((d) => !d)}>
          {detail ? "Hide full statistical detail" : "Show full statistical detail"}
        </button>
      </div>
      {detail && <DetailedBody m={m} />}
    </div>
  );
}

// The full, rigorous breakdown this page always showed: confidence intervals, every UNSURE
// treatment, the out-of-time check kept strictly separate, band tables and sensitivity. Unchanged
// from before this redesign, just moved behind a toggle so the dashboard above is the default view.
function DetailedBody({ m }) {
  const review = m.bands?.find((b) => b.name === "REVIEW") ?? null;
  return (
    <div className="space-y-6">
      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Held out evaluation</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <RangeStat title="Precision, AUTO only (headline)" range={m.precisionAutoOnly} />
          {m.precisionReviewBand || !review ? (
            <RangeStat title="Precision, REVIEW band" range={m.precisionReviewBand} />
          ) : (
            <Card>
              <p className="font-semibold">REVIEW band</p>
              <p>{review.counts.match} of {review.sampleSize} matched ({review.counts.noMatch} no match, {review.counts.unsure} unsure). All {review.bandSize} pairs were labeled, so these are counts and not an estimate.</p>
            </Card>
          )}
          <RangeStat title="Recall given blocking, AUTO only" range={m.recallAutoOnly} kind="recall" weighted />
          <Card>
            <p className="font-semibold">Blocking recall (30 held out holdings)</p>
            <p>{m.blockingRecall ? ci(m.blockingRecall) : NOT_YET}</p>
            {m.blockingRecall && <RangeBar ci={m.blockingRecall} />}
          </Card>
        </div>
        <Card>
          <p className="font-semibold">How UNSURE labels are counted</p>
          <p>UNSURE excluded is the headline. The worst case counts UNSURE as no match and the best case counts it as a match. The gap between them is the honest range.</p>
          <p>Raw UNSURE count: {m.unsureCount ?? NOT_YET}. Held out pairs: {m.heldOutCount ?? NOT_YET}.</p>
        </Card>
        <div className="grid gap-4 md:grid-cols-2">
          <RangeStat title="If REVIEW pairs were auto accepted, precision (optional)" range={m.precisionIfReviewAutoAccepted} weighted />
          <RangeStat title="If REVIEW pairs were auto accepted, recall (optional)" range={m.recallIfReviewAutoAccepted} kind="recall" weighted />
        </div>
        <p className="text-sm">Weighted figures resample only the sampled bands. For recall, counting UNSURE as no match gives the higher figure, so the two treatments are not a worst and best case.</p>
        <Card>
          <p className="mb-2 font-semibold">Per band</p>
          {m.bands ? <BandTable bands={m.bands} /> : <p>{NOT_YET}</p>}
          <p className="mt-2 text-sm">The table reports match rate, not precision. For the two bands below the threshold it is the share of true matches the matcher missed.</p>
        </Card>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Out of time check, separate from the held out figures</h2>
        {m.outOfTime ? (
          <>
            <p className="text-sm">A sample of the prior quarter, {m.outOfTime.periodEnd}, labeled after the matcher was frozen. Report only, never pooled with the held out evaluation. Raw UNSURE count: {m.outOfTime.unsureCount}. Labeled pairs: {m.outOfTime.labeledCount}.</p>
            <div className="grid gap-4 md:grid-cols-2">
              <RangeStat title="Precision, AUTO only, prior quarter" range={m.outOfTime.precisionAutoOnly} />
              <Card><BandTable bands={m.outOfTime.bands} /></Card>
            </div>
          </>
        ) : (
          <p>{NOT_YET}</p>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Evidence signals present</h2>
        <p className="text-sm">Descriptive and report only. A signal says a difference is disclosed in the filings. It does not explain or cause a gap.</p>
        <Card>
          <p className="mb-2 font-semibold">Signal lift</p>
          {m.evidenceLift ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead><tr><th className="p-1">Signal</th><th className="p-1">Flagged facilities with it</th><th className="p-1">Agreement facilities with it</th></tr></thead>
                <tbody>
                  {m.evidenceLift.map((r) => (
                    <tr key={r.code} className="border-t">
                      <td className="p-1">{SIGNAL_TEXT[r.code] ?? r.code}</td>
                      <td className="p-1">{pct(r.flaggedShare)} of {r.flaggedN}</td>
                      <td className="p-1">{pct(r.agreementShare)} of {r.agreementN}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p>{NOT_YET}</p>
          )}
        </Card>
        <Card>
          <p className="font-semibold">Unexplained share</p>
          <p>{m.unexplained ? `${m.unexplained.withoutSignal} of ${m.unexplained.flaggedN} flagged facilities carry no signal (${pct(m.unexplained.share)}). These need a manual look.` : NOT_YET}</p>
        </Card>
        <Card>
          <p className="mb-2 font-semibold">Field coverage</p>
          {m.fieldCoverage ? (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead><tr><th className="p-1">BDC</th><th className="p-1">Field</th><th className="p-1">Parsed</th><th className="p-1">Holdings</th></tr></thead>
                <tbody>
                  {m.fieldCoverage.map((r) => (
                    <tr key={r.bdcName + r.field} className="border-t"><td className="p-1">{r.bdcName}</td><td className="p-1">{FIELD_TEXT[r.field] ?? r.field}</td><td className="p-1">{pct(r.parsedShare)}</td><td className="p-1">{r.n}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p>{NOT_YET}</p>
          )}
          <p className="mt-2 text-sm">PIK reads as parsed for every holding because a missing PIK is stored as zero. It does not mean PIK was disclosed.</p>
        </Card>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">History links</h2>
        <Card>
          {m.historyLinks ? (
            <>
              <p>Prior quarter {m.historyLinks.priorPeriodEnd}. Share of compared holdings linked to the same holding one quarter earlier: {pct(m.historyLinks.linkedShare)}.</p>
              <p>Link accuracy from the hand check: {m.historyLinks.precision ? ci(m.historyLinks.precision.unsureExcluded) : NOT_YET}</p>
            </>
          ) : (
            <p>{NOT_YET}</p>
          )}
        </Card>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Divergence sensitivity</h2>
        <Card>
          {m.sensitivityTable ? (
            <p>{m.sensitivityTable.map((s) => `${s.thresholdPts} ${s.thresholdPts === 1 ? "point" : "points"}: ${s.flaggedCount} flagged`).join(". ")}.</p>
          ) : (
            <p>{NOT_YET}</p>
          )}
        </Card>
        <p className="text-sm">
          Coverage: {m.coverage.bdcs} BDCs, {m.coverage.quarters} quarters, {m.coverage.holdings} holdings in the measured quarter, {m.coverage.facilities} facilities. Measured quarter {m.coverage.measuredPeriodEnd}. Metrics cover the measured quarter only.
        </p>
      </section>
    </div>
  );
}
