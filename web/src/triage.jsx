import { useState } from "react";
import { Link, useParams } from "react-router";
import { ApiFailure, getJson } from "./api.js";
import { useShared } from "./App.jsx";
import { BarList, Card, CardLabel, EmptyState, LenderValueBars, Load, PeriodTag, StatCard, StatusDot, StatusPill, useFetch } from "./components.jsx";
import { fixed, points, SIGNAL_TEXT, typeName, usd } from "./format.js";

// Buckets of divergencePts, a field E4 already returns for every facility. Purely a client-side
// grouping of an existing number into fixed ranges, the same style as E9's own sensitivity
// thresholds (1, 2, 5 points); no new field, no invented category.
const DIFF_BUCKETS = [
  { label: "0-1 pts", min: 0, max: 1, color: "var(--color-chart-green)" },
  { label: "1-2 pts", min: 1, max: 2, color: "var(--color-chart-green-dark)" },
  { label: "2-5 pts", min: 2, max: 5, color: "var(--color-chart-yellow)" },
  { label: "5+ pts", min: 5, max: Infinity, color: "var(--color-chart-red)" },
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
                      { label: "Agreement", value: counts.agreement, color: "var(--color-chart-green)" },
                      { label: "Review", value: counts.mild, color: "var(--color-chart-yellow)" },
                      { label: "Flagged", value: counts.flagged, color: "var(--color-chart-red)" },
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
      <Link to="/facilities" className="mb-3 inline-block text-sm font-medium hover:underline" style={{ color: "var(--color-brand-dark)" }}>&larr; Back to Triage</Link>
      <Load f={f}>
        {(c) => {
          const hist = c.history;
          const priorBy = new Map(hist?.rows.map((r) => [r.bdcName, r.priorFairValuePctPar]) ?? []);
          return (
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="text-2xl font-bold uppercase leading-tight" style={{ color: "var(--color-text)" }}>{c.borrowerName}</h1>
                <StatusPill flag={c.divergenceFlag} />
                <PeriodTag periodEnd={c.periodEnd} measured={overview?.measuredPeriodEnd} />
              </div>

              <Card compact>
                <CardLabel>Current reported value</CardLabel>
                <LenderValueBars rows={c.rows.map((r) => ({ label: r.bdcName, value: Number(r.fairValuePctPar) }))} />
                <p className="mt-3 text-sm" style={{ color: "var(--color-text-secondary)" }}>Difference between lenders: {points(c.divergencePts)} points</p>
                {c.signals.length > 0 && (
                  <p className="mt-1.5 text-xs" style={{ color: "var(--color-text-muted)" }}>
                    Why the values may differ: {c.signals.map((s) => SIGNAL_TEXT[s] ?? s).join(", ")}
                  </p>
                )}
              </Card>

              <div className="grid gap-4 sm:grid-cols-2">
                <Card compact>
                  <CardLabel>Loan details</CardLabel>
                  <dl className="space-y-1.5 text-sm">
                    <div className="flex items-center justify-between gap-3">
                      <dt style={{ color: "var(--color-text-secondary)" }}>Loan type</dt>
                      <dd className="font-medium" style={{ color: "var(--color-text)" }}>{typeName(c.instrumentType)}</dd>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <dt style={{ color: "var(--color-text-secondary)" }}>Interest rate</dt>
                      <dd className="font-medium" style={{ color: "var(--color-text)" }}>{c.referenceRate ?? "Not disclosed"}</dd>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <dt style={{ color: "var(--color-text-secondary)" }}>Maturity</dt>
                      <dd className="font-medium" style={{ color: "var(--color-text)" }}>{c.maturityBucket ?? "Not disclosed"}</dd>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <dt style={{ color: "var(--color-text-secondary)" }}>Reporting period</dt>
                      <dd className="font-medium" style={{ color: "var(--color-text)" }}>{c.periodEnd}</dd>
                    </div>
                  </dl>
                </Card>

                <Card compact>
                  <CardLabel>Lender reports</CardLabel>
                  <div className="divide-y" style={{ borderColor: "var(--color-border)" }}>
                    {c.rows.map((r) => {
                      const prior = priorBy.get(r.bdcName);
                      return (
                        <div key={r.bdcName + r.sourceUrl} className="flex items-center justify-between gap-3 py-1.5 text-sm">
                          <div>
                            <span className="font-medium" style={{ color: "var(--color-text)" }}>{r.bdcName}</span>
                            {prior !== null && prior !== undefined && (
                              <span className="block text-[11px]" style={{ color: "var(--color-text-muted)" }}>
                                Previous: {Number(prior).toFixed(2)}% &rarr; Current: {fixed(r.fairValuePctPar, 2)}%
                              </span>
                            )}
                          </div>
                          <div className="shrink-0 text-right">
                            <span className="font-medium" style={{ color: "var(--color-text)" }}>{fixed(r.fairValuePctPar, 2)}%</span>
                            <span className="ml-2" style={{ color: "var(--color-text-secondary)" }}>{usd(r.principal)}</span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  {c.excludedCount > 0 && (
                    <p className="mt-2 text-xs" style={{ color: "var(--color-text-muted)" }}>
                      {c.excludedCount} {c.excludedCount === 1 ? "holding is" : "holdings are"} excluded for having no usable mark.
                    </p>
                  )}
                </Card>
              </div>
            </div>
          );
        }}
      </Load>
    </>
  );
}
