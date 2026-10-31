import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { ApiFailure, getJson } from "./api.js";
import { useShared } from "./App.jsx";
import { Banner, Card, DotPlot, EmptyState, EvidenceTable, ExposureTag, HistoryStrip, inputClass, inputStyle, Load, PageTitle, PeriodTag, PersistenceTag, SignalChip, StatusPill, useFetch } from "./components.jsx";
import { FLAG_TEXT, fixed, points, spreadRange, typeName } from "./format.js";
import { useDebounced } from "./pages.jsx";

// The only flag and sort values CONTRACT.md's E4 accepts. "All" sends no flag parameter at all.
const FLAG_CHIPS = [
  [undefined, "All"],
  ["AGREEMENT", "Agreement"],
  ["MILD", "Mild"],
  ["FLAGGED", "Flagged"],
];
const SORTS = [
  ["borrower", "Borrower"],
  ["exposure", "Exposure"],
];

// ------------------------------------------------------------------ 4.4 Triage (the Facilities page)
export function TriagePage() {
  const [params, setParams] = useSearchParams();
  const urlFlag = params.get("flag") ?? undefined;
  const urlSort = params.get("sort") === "exposure" ? "exposure" : "borrower";
  const [text, setText] = useState(params.get("search") ?? "");
  useEffect(() => setText(params.get("search") ?? ""), [params]);
  const q = useDebounced(text.trim());

  const setQuery = (next) => {
    const merged = { flag: urlFlag, sort: urlSort, search: params.get("search") ?? undefined, ...next };
    const clean = {};
    for (const [k, v] of Object.entries(merged)) if (v) clean[k] = v;
    setParams(clean, { replace: true });
  };

  useEffect(() => {
    // Keep the URL's search term in step with the debounced text, without fighting the user's typing.
    if (q !== (params.get("search") ?? "")) setQuery({ search: q || undefined });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const f = useFetch(
    () => getJson("/api/facilities", { flag: urlFlag, sort: urlSort, search: q || undefined }),
    [urlFlag, urlSort, q],
  );
  const { overview } = useShared();
  return (
    <>
      <PageTitle sub="Start with the cases where reported values differ the most">Triage</PageTitle>
      <div className="mb-5 flex flex-wrap items-center gap-3">
        <div role="group" aria-label="Filter by status" className="flex flex-wrap gap-2">
          {FLAG_CHIPS.map(([flag, label]) => (
            <button key={label} aria-pressed={urlFlag === flag} onClick={() => setQuery({ flag })} className="btn-secondary">
              {label}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-sm" style={{ color: "var(--color-text-secondary)" }}>
          Sort
          <select
            value={urlSort}
            onChange={(e) => setQuery({ sort: e.target.value === "exposure" ? "exposure" : undefined })}
            className="rounded-xl border px-2.5 py-1.5 text-sm outline-none focus:border-[var(--color-brand)]"
            style={inputStyle}
          >
            {SORTS.map(([v, label]) => (
              <option key={v} value={v}>{label}</option>
            ))}
          </select>
        </label>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Search borrower"
          aria-label="Search borrower"
          maxLength={200}
          className={`max-w-md flex-1 ${inputClass}`}
          style={inputStyle}
        />
      </div>
      <Load f={f}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState>No facilities match this filter.</EmptyState>
          ) : (
            <div className="space-y-4">
              {rows.map((x) => (
                <Card key={x.facilityId} to={`/facilities/${x.facilityId}`}>
                  <div className="flex flex-wrap justify-between gap-2">
                    <div>
                      <p className="font-semibold uppercase" style={{ color: "var(--color-text)" }}>{x.borrowerName}<PeriodTag periodEnd={x.periodEnd} measured={overview?.measuredPeriodEnd} /></p>
                      <p className="mt-1 text-sm" style={{ color: "var(--color-text-secondary)" }}>{typeName(x.instrumentType)}</p>
                      <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>{x.referenceRate ?? "Reference rate not disclosed"}, spread {spreadRange(x.spreadBps.min, x.spreadBps.max)}</p>
                      <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>{x.lenderCount} lenders</p>
                    </div>
                    <div className="text-right">
                      <p><StatusPill flag={x.divergenceFlag} /></p>
                      <p className="mt-1 text-sm font-medium" style={{ color: "var(--color-text)" }}>{points(x.divergencePts)} points</p>
                      <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}><ExposureTag exposureUsd={x.exposureUsd} /></p>
                      <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>{x.signalCount} {x.signalCount === 1 ? "signal" : "signals"}</p>
                      <p className="mt-1"><PersistenceTag persistence={x.persistence} /></p>
                    </div>
                  </div>
                  <p className="mt-3 text-sm font-medium" style={{ color: "var(--color-brand-dark)" }}>View comparison &rarr;</p>
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
  const f = useFetch(() => getJson(`/api/facilities/${encodeURIComponent(id)}/comparison`), [id]);
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
