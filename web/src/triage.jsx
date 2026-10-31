import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { ApiFailure, getJson } from "./api.js";
import { useShared } from "./App.jsx";
import { Card, CardLabel, EmptyState, EvidenceTable, ExposureTag, FLAG_STATUS, HistoryStrip, inputClass, inputStyle, LenderValueBars, Load, PageTitle, PeriodTag, PersistenceTag, SignalChip, SourceLink, StatusPill, useFetch } from "./components.jsx";
import { FLAG_TEXT, points, spreadRange, typeName } from "./format.js";
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
const VALUE_HEADLINE = {
  AGREEMENT: "Lenders agree",
  MILD: "Lenders show a mild difference",
  FLAGGED: "Lenders disagree",
};
const VALUE_EXPLAIN = {
  AGREEMENT: "The lenders' reported values are very close.",
  MILD: "The lenders' reported values differ somewhat.",
  FLAGGED: "The lenders' reported values differ significantly.",
};

export function ComparisonPage() {
  const { id = "" } = useParams();
  const f = useFetch(() => getJson(`/api/facilities/${encodeURIComponent(id)}/comparison`), [id]);
  const { overview } = useShared();
  if (f.state === "error" && f.error instanceof ApiFailure && f.error.status === 404) {
    return (
      <>
        <Link to="/facilities" className="text-sm font-medium hover:underline" style={{ color: "var(--color-brand-dark)" }}>&larr; Back to Triage</Link>
        <EmptyState>This facility is not in the current build.</EmptyState>
      </>
    );
  }
  return (
    <>
      <Link to="/facilities" className="mb-5 inline-block text-sm font-medium hover:underline" style={{ color: "var(--color-brand-dark)" }}>&larr; Back to Triage</Link>
      <Load f={f}>
        {(c) => {
          const hist = c.history;
          const priorBy = new Map(hist?.rows.map((r) => [r.bdcName, r.priorFairValuePctPar]) ?? []);
          const status = FLAG_STATUS[c.divergenceFlag] ?? { fg: "var(--color-text)", bg: "var(--color-border)" };
          return (
            <div className="space-y-6">
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-secondary)" }}>
                  {typeName(c.instrumentType)}{c.referenceRate ? ` · ${c.referenceRate}` : ""}{c.maturityBucket ? ` · Maturity bucket ${c.maturityBucket}` : ""}
                </p>
                <h1 className="text-[28px] font-bold uppercase leading-tight" style={{ color: "var(--color-text)" }}>{c.borrowerName}</h1>
                <p className="mt-1 text-sm" style={{ color: "var(--color-text-secondary)" }}>
                  Reporting period: {c.periodEnd}<PeriodTag periodEnd={c.periodEnd} measured={overview?.measuredPeriodEnd} />
                </p>
              </div>

              <div className="card-shadow rounded-[var(--radius-card)] border p-6" style={{ borderColor: "var(--color-border-strong)", background: status.bg }}>
                <CardLabel>Value check</CardLabel>
                <p className="flex items-center gap-2 text-xl font-bold" style={{ color: status.fg }}>
                  <span className="inline-block h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: status.dot }} />
                  {VALUE_HEADLINE[c.divergenceFlag] ?? FLAG_TEXT[c.divergenceFlag]}
                </p>
                <p className="mt-5 text-sm" style={{ color: "var(--color-text-secondary)" }}>Difference between reported values</p>
                <p className="mt-1 text-3xl font-bold" style={{ color: "var(--color-text)" }}>{points(c.divergencePts)} points</p>
                <p className="mt-3 text-sm" style={{ color: "var(--color-text-secondary)" }}>{VALUE_EXPLAIN[c.divergenceFlag] ?? ""}</p>
              </div>

              {c.signals.length > 0 && (
                <div>
                  <p className="mb-2 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-secondary)" }}>Signals present, not causes</p>
                  {c.signals.map((s) => <SignalChip key={s} code={s} />)}
                </div>
              )}

              <Card>
                <CardLabel>Current value reported by each lender</CardLabel>
                <LenderValueBars rows={c.rows.map((r) => ({ label: r.bdcName, value: Number(r.fairValuePctPar) }))} />
                <p className="mt-4 text-sm" style={{ color: "var(--color-text-secondary)" }}>Difference: {points(c.divergencePts)} percentage points</p>
              </Card>

              <Card>
                <CardLabel>How the reported values changed</CardLabel>
                {hist === null ? (
                  <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>Not yet measured</p>
                ) : (
                  <>
                    <HistoryStrip
                      persistence={hist.persistence}
                      rows={c.rows.map((r) => {
                        const p = priorBy.get(r.bdcName);
                        return { bdcName: r.bdcName, prior: p === null || p === undefined ? null : Number(p), current: Number(r.fairValuePctPar) };
                      })}
                    />
                    <p className="mt-2 text-sm" style={{ color: "var(--color-text-secondary)" }}>
                      {hist.priorDivergencePts === null ? `Fewer than 2 lenders have a linked mark on ${hist.priorPeriodEnd}, so there is no prior gap.` : `Gap on ${hist.priorPeriodEnd}: ${points(hist.priorDivergencePts)} points, ${FLAG_TEXT[hist.priorDivergenceFlag ?? ""] ?? ""}.`}
                    </p>
                    <p className="mt-1 text-xs" style={{ color: "var(--color-text-muted)" }}>Only two reporting periods are available.</p>
                  </>
                )}
              </Card>

              <Card>
                <CardLabel>Loan details</CardLabel>
                <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--color-text-muted)" }}>Loan type</p>
                    <p className="mt-0.5 text-sm" style={{ color: "var(--color-text)" }}>{typeName(c.instrumentType)}</p>
                  </div>
                  <div className="border-t pt-4 sm:border-t-0 sm:pt-0" style={{ borderColor: "var(--color-border)" }}>
                    <p className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--color-text-muted)" }}>Interest rate</p>
                    <p className="mt-0.5 text-sm" style={{ color: "var(--color-text)" }}>{c.referenceRate ?? "Reference rate not disclosed"}</p>
                  </div>
                  <div className="border-t pt-4" style={{ borderColor: "var(--color-border)" }}>
                    <p className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--color-text-muted)" }}>Maturity</p>
                    <p className="mt-0.5 text-sm" style={{ color: "var(--color-text)" }}>{c.maturityBucket ?? "Not disclosed"}</p>
                  </div>
                  <div className="border-t pt-4" style={{ borderColor: "var(--color-border)" }}>
                    <p className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--color-text-muted)" }}>Reporting period</p>
                    <p className="mt-0.5 text-sm" style={{ color: "var(--color-text)" }}>{c.periodEnd}</p>
                  </div>
                </div>
              </Card>

              <Card>
                <CardLabel>Lender reports</CardLabel>
                <EvidenceTable rows={c.rows} />
                {c.excludedCount > 0 && (
                  <p className="mt-3 text-sm" style={{ color: "var(--color-text-secondary)" }}>
                    Note: {c.excludedCount} {c.excludedCount === 1 ? "holding is" : "holdings are"} excluded because {c.excludedCount === 1 ? "it has" : "they have"} no usable mark.
                  </p>
                )}
              </Card>

              <Card>
                <CardLabel>Source</CardLabel>
                <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>These figures come from the lenders' SEC filings.</p>
                <ul className="mt-3 divide-y" style={{ borderColor: "var(--color-border)" }}>
                  {c.rows.map((r) => (
                    <li key={r.bdcName + r.sourceUrl} className="flex items-center justify-between py-2 text-sm" style={{ borderColor: "var(--color-border)" }}>
                      <span style={{ color: "var(--color-text)" }}>{r.bdcName}</span>
                      <SourceLink url={r.sourceUrl}>View filing</SourceLink>
                    </li>
                  ))}
                </ul>
              </Card>
            </div>
          );
        }}
      </Load>
    </>
  );
}
