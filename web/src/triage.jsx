import { useState } from "react";
import { Link, useParams } from "react-router";
import { ApiFailure, getJson } from "./api.js";
import { useShared } from "./App.jsx";
import { BarList, Card, CardLabel, EmptyState, EvidenceTable, FLAG_STATUS, HistoryStrip, LenderValueBars, Load, PeriodTag, SignalChip, SourceLink, StatCard, StatusDot, useFetch } from "./components.jsx";
import { FLAG_TEXT, NOT_YET, points, typeName, usd } from "./format.js";

// Buckets of divergencePts, a field E4 already returns for every facility. Purely a client-side
// grouping of an existing number into fixed ranges, the same style as E9's own sensitivity
// thresholds (1, 2, 5 points); no new field, no invented category.
const DIFF_BUCKETS = [
  { label: "0-1 pts", min: 0, max: 1, color: "var(--color-brand)" },
  { label: "1-2 pts", min: 1, max: 2, color: "var(--color-brand-dark)" },
  { label: "2-5 pts", min: 2, max: 5, color: "var(--color-review)" },
  { label: "5+ pts", min: 5, max: Infinity, color: "var(--color-flagged)" },
];
const FACILITY_FILTERS = [
  ["all", "All"],
  ["AGREEMENT", "Agreement"],
  ["MILD", "Review"],
  ["FLAGGED", "Flagged"],
  ["multi", "2+ lenders"],
];
const FACILITY_PAGE_SIZE = 6;

// ------------------------------------------------------------------ 4.4 Triage (the Facilities page)
export function TriagePage() {
  // One unfiltered fetch (E4, sort=exposure, no flag or search parameter) drives the KPI tiles,
  // both charts and the table; the filter pills and "2+ lenders" slice this same list client side,
  // so switching between them does not refetch.
  const f = useFetch(() => getJson("/api/facilities", { sort: "exposure" }), []);
  const [filter, setFilter] = useState("all");
  const [visible, setVisible] = useState(FACILITY_PAGE_SIZE);
  const { overview } = useShared();

  return (
    <>
      <div className="mb-4">
        <h1 className="text-2xl font-bold uppercase tracking-wide" style={{ color: "var(--color-text)" }}>Facilities</h1>
        <p className="mt-0.5 text-sm" style={{ color: "var(--color-text-secondary)" }}>
          Loans reported by the monitored lenders &middot; Reporting period: {overview?.measuredPeriodEnd ?? NOT_YET}
        </p>
      </div>

      <Load f={f}>
        {(allRows) => {
          const counts = { agreement: 0, mild: 0, flagged: 0 };
          for (const r of allRows) {
            if (r.divergenceFlag === "FLAGGED") counts.flagged += 1;
            else if (r.divergenceFlag === "MILD") counts.mild += 1;
            else counts.agreement += 1;
          }
          const total = allRows.length;
          const pct = (n) => (total === 0 ? "0%" : `${Math.round((n / total) * 100)}%`);

          const bucketRows = DIFF_BUCKETS.map((b) => ({
            label: b.label,
            color: b.color,
            value: allRows.filter((r) => {
              const p = Number(r.divergencePts);
              return p >= b.min && (b.max === Infinity ? true : p < b.max);
            }).length,
          }));

          const filtered = allRows.filter((r) => {
            if (filter === "multi") return r.lenderCount >= 2;
            if (filter === "AGREEMENT" || filter === "MILD" || filter === "FLAGGED") return r.divergenceFlag === filter;
            return true;
          });
          const shown = filtered.slice(0, visible);

          return (
            <>
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <StatCard compact label="Facilities" value={total} tone="neutral" onClick={() => setFilter("all")} />
                <StatCard compact label="Agreement" value={counts.agreement} note={pct(counts.agreement)} tone="brand" onClick={() => setFilter("AGREEMENT")} />
                <StatCard compact label="Review" value={counts.mild} note={pct(counts.mild)} tone="review" onClick={() => setFilter("MILD")} />
                <StatCard compact label="Flagged" value={counts.flagged} note={pct(counts.flagged)} tone="flagged" onClick={() => setFilter("FLAGGED")} />
              </div>

              <div className="mt-3 grid gap-3 lg:grid-cols-2">
                <Card compact>
                  <CardLabel>Facilities by status</CardLabel>
                  <BarList
                    compact
                    rows={[
                      { label: "Agreement", value: counts.agreement, color: "var(--color-brand)" },
                      { label: "Review", value: counts.mild, color: "var(--color-review)" },
                      { label: "Flagged", value: counts.flagged, color: "var(--color-flagged)" },
                    ]}
                  />
                </Card>
                <Card compact>
                  <CardLabel>Value difference</CardLabel>
                  <BarList compact rows={bucketRows} />
                </Card>
              </div>

              <div role="group" aria-label="Filter facilities" className="mt-3 flex flex-wrap gap-2">
                {FACILITY_FILTERS.map(([v, label]) => (
                  <button key={v} aria-pressed={filter === v} onClick={() => setFilter(v)} className="btn-secondary">
                    {label}
                  </button>
                ))}
              </div>

              <Card compact className="mt-3">
                <CardLabel>Facility directory</CardLabel>
                {filtered.length === 0 ? (
                  <EmptyState>No facilities match this filter.</EmptyState>
                ) : (
                  <>
                    <div className="overflow-x-auto">
                      <table className="w-full text-left text-sm">
                        <thead>
                          <tr style={{ color: "var(--color-text-secondary)" }}>
                            <th className="py-2 pr-4 font-medium">Facility / Borrower</th>
                            <th className="py-2 pr-4 font-medium">Lenders</th>
                            <th className="py-2 pr-4 font-medium" title="Ranking key, not an estimate of loss">Exposure</th>
                            <th className="py-2 pr-4 font-medium">Difference</th>
                            <th className="py-2 pr-4 font-medium">Status</th>
                            <th className="py-2 pr-2 font-medium">Action</th>
                          </tr>
                        </thead>
                        <tbody>
                          {shown.map((r) => (
                            <tr key={r.facilityId} className="table-row-hover border-t transition-colors" style={{ borderColor: "var(--color-border)" }}>
                              <td className="py-2 pr-4">
                                <span className="font-medium" style={{ color: "var(--color-text)" }}>{r.borrowerName}</span>
                                <span className="ml-1 text-xs" style={{ color: "var(--color-text-muted)" }}>{typeName(r.instrumentType)}</span>
                                <PeriodTag periodEnd={r.periodEnd} measured={overview?.measuredPeriodEnd} />
                              </td>
                              <td className="py-2 pr-4" style={{ color: "var(--color-text)" }}>{r.lenderCount}</td>
                              <td className="py-2 pr-4" style={{ color: "var(--color-text)" }}>{usd(r.exposureUsd)}</td>
                              <td className="py-2 pr-4" style={{ color: "var(--color-text)" }}>{points(r.divergencePts)} pts</td>
                              <td className="py-2 pr-4"><StatusDot flag={r.divergenceFlag} label={r.divergenceFlag === "MILD" ? "Review" : undefined} /></td>
                              <td className="py-2 pr-2">
                                <Link to={`/facilities/${r.facilityId}`} className="text-sm font-medium hover:underline" style={{ color: "var(--color-brand-dark)" }}>
                                  View &rarr;
                                </Link>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="mt-3 flex items-center justify-between">
                      <span className="text-xs" style={{ color: "var(--color-text-muted)" }}>Showing {shown.length} of {filtered.length}</span>
                      {visible < filtered.length && (
                        <button className="btn-secondary" onClick={() => setVisible(filtered.length)}>
                          View all &rarr;
                        </button>
                      )}
                    </div>
                  </>
                )}
              </Card>
            </>
          );
        }}
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
