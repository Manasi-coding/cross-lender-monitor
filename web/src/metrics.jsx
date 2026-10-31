import { getJson } from "./api.js";
import { BandTable, Card, Load, PageTitle, RangeStat, ci, useFetch } from "./components.jsx";
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
      <PageTitle sub="Held out evaluation of the matcher on the measured quarter. Recall is given blocking. No figure includes review queue confirmations.">Metrics</PageTitle>
      <Load f={f}>{(m) => <Body m={m} />}</Load>
    </>
  );
}

function Body({ m }) {
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
