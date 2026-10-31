import { useState } from "react";
import { Link, useParams } from "react-router";
import { ApiFailure, getJson } from "./api";
import { useShared } from "./App";
import { Banner, Card, DotPlot, EmptyState, EvidenceTable, ExposureTag, HistoryStrip, Load, PageTitle, PeriodTag, PersistenceTag, SignalChip, useFetch } from "./components";
import { FLAG_TEXT, fixed, points, spreadRange, typeName } from "./format";
import type { Comparison, FacilityItem } from "./types";
import { useDebounced } from "./pages";

// ------------------------------------------------------------------ 4.4 Triage (the Facilities page)
export function TriagePage() {
  const [view, setView] = useState<"flagged" | "all">("flagged");
  const [text, setText] = useState("");
  const q = useDebounced(text.trim());
  // only valid parameter values are ever sent: flag is FLAGGED or absent, sort is exposure or absent
  const f = useFetch(
    () => getJson<FacilityItem[]>("/api/facilities", view === "flagged" ? { flag: "FLAGGED", sort: "exposure", search: q || undefined } : { search: q || undefined }),
    [view, q],
  );
  const { overview } = useShared();
  return (
    <>
      <PageTitle>Triage</PageTitle>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div role="group" aria-label="View">
          {(["flagged", "all"] as const).map((v) => (
            <button key={v} aria-pressed={view === v} onClick={() => setView(v)} className={`border px-3 py-1 ${view === v ? "bg-gray-800 text-white dark:bg-gray-200 dark:text-black" : ""}`}>
              {v === "flagged" ? "Flagged" : "All"}
            </button>
          ))}
        </div>
        <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Search borrower" aria-label="Search borrower" maxLength={200} className="w-full max-w-md rounded border px-3 py-1" />
      </div>
      <Load f={f}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState>{view === "flagged" ? "No flagged facilities match this search." : "No facilities match this search."}</EmptyState>
          ) : (
            <div className="space-y-4">
              {rows.map((x) => (
                <Card key={x.facilityId} to={`/facilities/${x.facilityId}`}>
                  <div className="flex flex-wrap justify-between gap-2">
                    <div>
                      <p className="font-bold uppercase">{x.borrowerName}<PeriodTag periodEnd={x.periodEnd} measured={overview?.measuredPeriodEnd} /></p>
                      <p>{typeName(x.instrumentType)}</p>
                      <p>{x.referenceRate ?? "Reference rate not disclosed"}, spread {spreadRange(x.spreadBps.min, x.spreadBps.max)}</p>
                      <p>{x.lenderCount} lenders</p>
                    </div>
                    <div className="text-right">
                      <p className="font-semibold">{FLAG_TEXT[x.divergenceFlag]}, {points(x.divergencePts)} points</p>
                      <p><ExposureTag exposureUsd={x.exposureUsd} /></p>
                      <p>{x.signalCount} {x.signalCount === 1 ? "signal" : "signals"}</p>
                      <p><PersistenceTag persistence={x.persistence} /></p>
                    </div>
                  </div>
                  <p className="mt-2 underline">View comparison</p>
                </Card>
              ))}
            </div>
          )
        }
      </Load>
    </>
  );
}

// ------------------------------------------------------------------ 4.5 Facility comparison
export function ComparisonPage() {
  const { id = "" } = useParams();
  const f = useFetch(() => getJson<Comparison>(`/api/facilities/${encodeURIComponent(id)}/comparison`), [id]);
  const { overview } = useShared();
  if (f.state === "error" && f.error instanceof ApiFailure && f.error.status === 404) {
    return (
      <>
        <Link to="/facilities" className="underline">Back to triage</Link>
        <EmptyState>This facility is not in the current build.</EmptyState>
      </>
    );
  }
  return (
    <>
      <Link to="/facilities" className="underline">Back to triage</Link>
      <Load f={f}>
        {(c) => {
          const hist = c.history;
          const priorBy = new Map(hist?.rows.map((r) => [r.bdcName, r.priorFairValuePctPar]) ?? []);
          return (
            <div className="space-y-4">
              <PageTitle sub={<>{typeName(c.instrumentType)}. {c.referenceRate ?? "Reference rate not disclosed"}, maturity bucket {c.maturityBucket ?? "Not disclosed"}. Period end: {c.periodEnd}<PeriodTag periodEnd={c.periodEnd} measured={overview?.measuredPeriodEnd} /></>}>
                <span className="uppercase">{c.borrowerName}</span>
              </PageTitle>
              <Banner flag={c.divergenceFlag} points={c.divergencePts} />
              <p><ExposureTag exposureUsd={c.exposureUsd} /></p>
              <section>
                <h2 className="mb-2 text-lg font-semibold">Lender comparison and evidence</h2>
                <p className="mb-2 text-sm">Signals present, not causes:</p>
                <p className="mb-2">{c.signals.length === 0 ? "No signals present in the disclosed fields." : c.signals.map((s) => <SignalChip key={s} code={s} />)}</p>
                <EvidenceTable rows={c.rows} />
                {c.excludedCount > 0 && <p className="mt-2 text-sm">Note: {c.excludedCount} {c.excludedCount === 1 ? "holding is" : "holdings are"} excluded because {c.excludedCount === 1 ? "it has" : "they have"} no usable mark.</p>}
              </section>
              <div className="grid gap-4 md:grid-cols-2">
                <Card>
                  <h2 className="mb-2 font-semibold">Fair value as a percent of par</h2>
                  <DotPlot rows={c.rows.map((r) => ({ label: r.bdcName.split(" ")[0], value: Number(r.fairValuePctPar) }))} />
                </Card>
                <Card>
                  <h2 className="mb-2 font-semibold">Facility details</h2>
                  <p>Instrument: {typeName(c.instrumentType)}</p>
                  <p>Rate: {c.referenceRate ?? "Reference rate not disclosed"}</p>
                  <p>Maturity bucket: {c.maturityBucket ?? "Not disclosed"}</p>
                  <p>Divergence: {fixed(c.divergencePts, 2)} points</p>
                </Card>
              </div>
              <Card>
                <h2 className="mb-2 font-semibold">History</h2>
                {hist === null ? (
                  <p>Not yet measured</p>
                ) : (
                  <>
                    <HistoryStrip
                      persistence={hist.persistence}
                      rows={c.rows.map((r) => {
                        const p = priorBy.get(r.bdcName);
                        return { bdcName: r.bdcName, prior: p === null || p === undefined ? null : Number(p), current: Number(r.fairValuePctPar) };
                      })}
                    />
                    <p className="mt-2 text-sm">
                      {hist.priorDivergencePts === null ? `Fewer than 2 lenders have a linked mark on ${hist.priorPeriodEnd}, so there is no prior gap.` : `Gap on ${hist.priorPeriodEnd}: ${points(hist.priorDivergencePts)} points, ${FLAG_TEXT[hist.priorDivergenceFlag ?? ""] ?? ""}.`}
                    </p>
                  </>
                )}
              </Card>
            </div>
          );
        }}
      </Load>
    </>
  );
}
