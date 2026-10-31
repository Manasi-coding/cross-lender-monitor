import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { ApiFailure, getJson } from "./api.js";
import { useShared } from "./App.jsx";
import {
  Card,
  CardLabel,
  ClickableDivergenceBar,
  DivergenceDonut,
  DivergenceSplitChart,
  EmptyState,
  ErrorState,
  FLAG_STATUS,
  HeroCard,
  HeroLink,
  inputClass,
  inputStyle,
  Load,
  PageTitle,
  PeriodTag,
  RankedShareList,
  Skeleton,
  SourceLink,
  StatCard,
  StatusDot,
  StatusPill,
  useFetch,
} from "./components.jsx";
import { NOT_YET, points, typeName, usd } from "./format.js";
export function useDebounced(value, ms = 300) {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

const share = (n, total) => (total === 0 ? NOT_YET : `${((n / total) * 100).toFixed(1)}%`);

// ------------------------------------------------------------------ 4.1 Overview
export function OverviewPage() {
  const { overview: o, failed, refresh } = useShared();
  // Reuses the existing E4 facilities endpoint (flag=FLAGGED, sort=exposure) to drive the "biggest differences"
  // and "cases worth looking at first" sections below. No new endpoint, no invented figures.
  const flagged = useFetch(() => getJson("/api/facilities", { flag: "FLAGGED", sort: "exposure" }), []);

  if (!o) {
    return (
      <>
        <PageTitle>Overview</PageTitle>
        {failed ? <ErrorState error={{ message: "The overview could not be loaded." }} retry={refresh} /> : <Skeleton />}
      </>
    );
  }

  const s = o.divergenceSplit;
  const total = s ? s.agreement + s.mild + s.flagged : 0;
  const agreementShare = s && total > 0 ? share(s.agreement, total) : NOT_YET;
  const agreementPctNum = s && total > 0 ? (s.agreement / total) * 100 : null;
  const flaggedRows = flagged.state === "ready" ? flagged.data : [];
  const topCases = flaggedRows.slice(0, 5);
  const topExposureByBorrower = flaggedRows.slice(0, 5).map((r) => ({ label: r.borrowerName, value: Number(r.exposureUsd) }));

  return (
    <>
      <PageTitle>Overview</PageTitle>

      <HeroCard
        eyebrow={`Measured quarter · ${o.measuredPeriodEnd}`}
        actions={
          <>
            <HeroLink to="/borrowers">Browse borrowers</HeroLink>
            <HeroLink to="/review">Review queue ({o.pendingReviewCount})</HeroLink>
          </>
        }
      />

      <div className="mt-6 grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="Facilities"
          countTo={o.facilityCount}
          format={(v) => Math.round(v)}
          to="/facilities"
          note={`Across ${o.bdcCount} ${o.bdcCount === 1 ? "lender" : "lenders"}`}
          tone="neutral"
        />
        <StatCard label="Need review" countTo={o.pendingReviewCount} format={(v) => Math.round(v)} to="/review" note="Need a closer look" tone="review" />
        <StatCard
          label="Flagged exposure"
          countTo={o.flaggedExposureUsd === null ? NaN : Number(o.flaggedExposureUsd)}
          format={(v) => usd(String(v))}
          value={usd(o.flaggedExposureUsd)}
          to="/facilities"
          note="Ranking key, not loss"
          tone="flagged"
        />
        <StatCard
          label="Agreement"
          countTo={agreementPctNum === null ? NaN : agreementPctNum}
          format={(v) => `${v.toFixed(1)}%`}
          value={agreementShare}
          to="/metrics"
          note="Valuations are close"
          tone="brand"
        />
      </div>

      <div className="mt-6 grid gap-5 lg:grid-cols-[2fr_3fr]">
        <Card>
          <CardLabel>Valuation differences</CardLabel>
          {s ? (
            <>
              <DivergenceDonut agreement={s.agreement} mild={s.mild} flagged={s.flagged} />
              <div className="mt-5 border-t pt-4" style={{ borderColor: "var(--color-border)" }}>
                <ClickableDivergenceBar agreement={s.agreement} mild={s.mild} flagged={s.flagged} />
              </div>
            </>
          ) : (
            <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>{NOT_YET}</p>
          )}
        </Card>
        <Card>
          <CardLabel>Biggest differences</CardLabel>
          <Load f={flagged}>
            {() =>
              topExposureByBorrower.length === 0 ? (
                <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>No flagged cases right now.</p>
              ) : (
                <>
                  <RankedShareList rows={topExposureByBorrower} total={Number(o.flaggedExposureUsd ?? 0)} />
                  <Link to="/facilities" className="mt-4 inline-block text-sm font-medium hover:underline" style={{ color: "var(--color-brand-dark)" }}>
                    More cases &rarr;
                  </Link>
                </>
              )
            }
          </Load>
        </Card>
      </div>

      <Card className="mt-6">
        <CardLabel>Cases worth looking at first</CardLabel>
        <Load f={flagged}>
          {() =>
            topCases.length === 0 ? (
              <EmptyState>No flagged cases right now.</EmptyState>
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr style={{ color: "var(--color-text-secondary)" }}>
                        <th className="py-2 pr-4 font-medium">Borrower</th>
                        <th className="py-2 pr-4 font-medium">Difference</th>
                        <th className="py-2 pr-4 font-medium">Exposure</th>
                        <th className="py-2 pr-4 font-medium">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {topCases.map((r) => (
                        <tr key={r.facilityId} className="table-row-hover border-t transition-colors" style={{ borderColor: "var(--color-border)" }}>
                          <td className="py-2.5 pr-4">
                            <Link to={`/facilities/${r.facilityId}`} className="font-medium hover:underline" style={{ color: "var(--color-text)" }}>
                              {r.borrowerName}
                            </Link>
                          </td>
                          <td className="py-2.5 pr-4" style={{ color: "var(--color-text)" }}>{points(r.divergencePts)} pts</td>
                          <td className="py-2.5 pr-4" style={{ color: "var(--color-text)" }}>{usd(r.exposureUsd)}</td>
                          <td className="py-2.5 pr-4"><StatusPill flag={r.divergenceFlag} /></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Link to="/facilities" className="mt-4 inline-block text-sm font-medium hover:underline" style={{ color: "var(--color-brand-dark)" }}>
                  View all flagged cases &rarr;
                </Link>
              </>
            )
          }
        </Load>
      </Card>

      <Card className="mt-6">
        <CardLabel>Data coverage</CardLabel>
        <p className="text-sm" style={{ color: "var(--color-text)" }}>
          {o.bdcCount} {o.bdcCount === 1 ? "lender" : "lenders"}
          <span style={{ color: "var(--color-text-muted)" }}> &nbsp;&middot;&nbsp; </span>
          {o.quarterCount} {o.quarterCount === 1 ? "quarter" : "quarters"}
          <span style={{ color: "var(--color-text-muted)" }}> &nbsp;&middot;&nbsp; </span>
          {o.facilityCount} facilities
          <span style={{ color: "var(--color-text-muted)" }}> &nbsp;&middot;&nbsp; </span>
          <span style={{ color: "var(--color-text-secondary)" }}>Latest: {o.measuredPeriodEnd}</span>
        </p>
      </Card>
    </>
  );
}

// The worst (highest) divergence flag across a borrower's facilities, and the point gap of that
// worst facility, used only to badge and sketch a borrower card. AGREEMENT < MILD < FLAGGED.
// Derived client-side from the existing E4 list (no flag filter, the same set Triage's "All" view
// uses and Borrowers already fetched); no new endpoint, no invented figures.
const SEVERITY = { AGREEMENT: 0, MILD: 1, FLAGGED: 2 };
function worstByBorrower(facilities) {
  const map = new Map();
  for (const f of facilities) {
    const prev = map.get(f.borrowerName);
    if (!prev || SEVERITY[f.divergenceFlag] > SEVERITY[prev.flag]) {
      map.set(f.borrowerName, { flag: f.divergenceFlag, pts: Number(f.divergencePts) });
    }
  }
  return map;
}

const BORROWER_FILTERS = [
  ["all", "All"],
  ["flagged", "Flagged"],
  ["multi", "2+ lenders"],
];
const DIRECTORY_PAGE_SIZE = 12;

// A thin horizontal bar sized by a facility's point gap, coloured by its status. A compact stand-in
// for the full value chart shown on the Comparison page, using the same divergencePts already
// fetched for this list (not a new value).
function DifferenceBar({ pts, flag }) {
  const s = FLAG_STATUS[flag] ?? { dot: "var(--color-text-muted)" };
  const widthPct = Math.min(100, (pts / 20) * 100);
  return (
    <div>
      <div className="h-1.5 w-full overflow-hidden rounded-full" style={{ background: "var(--color-border)" }}>
        <div className="h-full rounded-full" style={{ width: `${Math.max(widthPct, 3)}%`, background: s.dot }} />
      </div>
      <p className="mt-1.5 text-xs" style={{ color: "var(--color-text-secondary)" }}>Difference between lenders: {points(pts)} points</p>
    </div>
  );
}

// ------------------------------------------------------------------ 4.2 Borrowers
export function BorrowersPage() {
  const [params] = useSearchParams();
  const search = params.get("search") ?? "";
  const f = useFetch(() => getJson("/api/borrowers", { search: search || undefined }), [search]);
  // Reuses the same unfiltered E4 list Triage's "All" view uses, to badge each borrower card with
  // its worst facility status and point gap. No new endpoint and no parameter CONTRACT.md does not define.
  const facilities = useFetch(() => getJson("/api/facilities", {}), []);
  const [filter, setFilter] = useState("all");
  const [visible, setVisible] = useState(DIRECTORY_PAGE_SIZE);
  const { overview } = useShared();

  useEffect(() => setVisible(DIRECTORY_PAGE_SIZE), [search, filter]);

  const worstByName = facilities.state === "ready" ? worstByBorrower(facilities.data) : new Map();

  return (
    <>
      <PageTitle sub="Companies appearing across the monitored lenders">Borrowers</PageTitle>

      <Load f={f}>
        {(allRows) => {
          const multiLender = allRows.filter((b) => b.lenderCount >= 2).length;
          const flaggedCount = allRows.filter((b) => worstByName.get(b.canonicalName)?.flag === "FLAGGED").length;
          const statusCounts = { agreement: 0, mild: 0, flagged: 0 };
          for (const b of allRows) {
            const flag = worstByName.get(b.canonicalName)?.flag;
            if (flag === "FLAGGED") statusCounts.flagged += 1;
            else if (flag === "MILD") statusCounts.mild += 1;
            else if (flag === "AGREEMENT") statusCounts.agreement += 1;
          }

          const rows = allRows.filter((b) => {
            if (filter === "multi") return b.lenderCount >= 2;
            if (filter === "flagged") return worstByName.get(b.canonicalName)?.flag === "FLAGGED";
            return true;
          });
          const shown = rows.slice(0, visible);

          return (
            <>
              <div className="mt-2 grid gap-5 sm:grid-cols-3">
                <StatCard label="Total borrowers" value={allRows.length} note="companies" tone="neutral" onClick={() => setFilter("all")} />
                <StatCard label="Across lenders" value={multiLender} note="appear in 2+ lenders" tone="brand" onClick={() => setFilter("multi")} />
                <StatCard label="Flagged" value={flaggedCount} note="need a closer look" tone="flagged" onClick={() => setFilter("flagged")} />
              </div>

              <Card className="mt-5">
                <CardLabel>Borrowers by status</CardLabel>
                {facilities.state === "ready" ? (
                  <DivergenceSplitChart agreement={statusCounts.agreement} mild={statusCounts.mild} flagged={statusCounts.flagged} />
                ) : (
                  <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>{NOT_YET}</p>
                )}
              </Card>

              <div role="group" aria-label="Filter borrowers" className="mt-6 flex flex-wrap gap-2">
                {BORROWER_FILTERS.map(([v, label]) => (
                  <button key={v} aria-pressed={filter === v} onClick={() => setFilter(v)} className="btn-secondary">
                    {label}
                  </button>
                ))}
              </div>

              <h2 className="mb-4 mt-6 text-lg font-semibold" style={{ color: "var(--color-text)" }}>Borrower directory</h2>

              {rows.length === 0 ? (
                <EmptyState>No borrowers match this search.</EmptyState>
              ) : (
                <>
                  <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                    {shown.map((b) => {
                      const worst = worstByName.get(b.canonicalName);
                      const s = worst ? FLAG_STATUS[worst.flag] : null;
                      return (
                        <Link
                          key={b.canonicalBorrowerId}
                          to={`/borrowers/${b.canonicalBorrowerId}`}
                          className="card-shadow block rounded-[var(--radius-card)] border-2 p-5 transition-colors hover:brightness-[0.98]"
                          style={{ borderColor: s ? s.dot : "var(--color-border-strong)", background: s ? s.faint : "var(--color-surface)" }}
                        >
                          <p className="font-semibold uppercase" style={{ color: "var(--color-text)" }}>{b.canonicalName}</p>
                          <p className="mt-1 text-sm" style={{ color: "var(--color-text-secondary)" }}>
                            {b.lenderCount} {b.lenderCount === 1 ? "lender" : "lenders"} &middot; {b.facilityCount} {b.facilityCount === 1 ? "facility" : "facilities"}
                            <PeriodTag periodEnd={b.periodEnd} measured={overview?.measuredPeriodEnd} />
                          </p>
                          {worst && (
                            <div className="mt-3">
                              <DifferenceBar pts={worst.pts} flag={worst.flag} />
                            </div>
                          )}
                          <p className="mt-3">{worst ? <StatusPill flag={worst.flag} /> : <span className="text-xs" style={{ color: "var(--color-text-muted)" }}>No comparison yet</span>}</p>
                          <p className="mt-3 text-sm font-medium" style={{ color: "var(--color-brand-dark)" }}>View borrower &rarr;</p>
                        </Link>
                      );
                    })}
                  </div>
                  {visible < rows.length && (
                    <div className="mt-5 text-center">
                      <button className="btn-secondary" onClick={() => setVisible((v) => v + DIRECTORY_PAGE_SIZE)}>
                        Show more ({rows.length - visible} more)
                      </button>
                    </div>
                  )}
                </>
              )}
            </>
          );
        }}
      </Load>
    </>
  );
}

// ------------------------------------------------------------------ 4.3 Borrower detail
export function BorrowerDetailPage() {
  const { id = "" } = useParams();
  const f = useFetch(() => getJson(`/api/borrowers/${encodeURIComponent(id)}/facilities`), [id]);
  const { overview } = useShared();
  if (f.state === "error" && f.error instanceof ApiFailure && f.error.status === 404) {
    return (
      <>
        <Link to="/borrowers" className="text-sm font-medium hover:underline" style={{ color: "var(--color-brand-dark)" }}>&larr; Borrowers</Link>
        <EmptyState>This borrower is not in the current build.</EmptyState>
      </>
    );
  }
  return (
    <>
      <Link to="/borrowers" className="mb-4 inline-block text-sm font-medium hover:underline" style={{ color: "var(--color-brand-dark)" }}>&larr; Back to borrowers</Link>
      <Load f={f}>
        {(b) => (
          <>
            <PageTitle sub={<>{b.lenderCount} lenders, {b.facilityCount} facilities. Period end {b.periodEnd}<PeriodTag periodEnd={b.periodEnd} measured={overview?.measuredPeriodEnd} /></>}>
              <span className="uppercase">{b.canonicalName}</span>
            </PageTitle>
            <div className="space-y-4">
              {b.facilities.map((x) => (
                <Card key={x.facilityId} to={`/facilities/${x.facilityId}`}>
                  <p className="font-semibold" style={{ color: "var(--color-text)" }}>{typeName(x.instrumentType)}</p>
                  <p className="mt-1 text-sm" style={{ color: "var(--color-text-secondary)" }}>{x.referenceRate ?? "Reference rate not disclosed"}, maturity bucket {x.maturityBucket ?? "Not disclosed"}</p>
                  <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>{x.lenderCount} lenders</p>
                  <p className="mt-2 text-sm font-medium" style={{ color: "var(--color-brand-dark)" }}>View comparison &rarr;</p>
                </Card>
              ))}
            </div>
          </>
        )}
      </Load>
    </>
  );
}

// A filing's period end as a quarter label, e.g. 2026-06-30 -> "Q2 2026". Display only.
function quarterLabel(periodEnd) {
  const [y, m] = periodEnd.split("-").map(Number);
  return `Q${Math.ceil(m / 3)} ${y}`;
}

// ------------------------------------------------------------------ 4.8 Filings
export function FilingsPage() {
  const f = useFetch(() => getJson("/api/filings"), []);
  const [lender, setLender] = useState("");
  const [quarter, setQuarter] = useState("");
  const [formType, setFormType] = useState("");
  const [selected, setSelected] = useState(null);
  const { overview } = useShared();

  return (
    <>
      <PageTitle>Filings</PageTitle>
      <Load f={f}>
        {(rows) => {
          const lenders = [...new Set(rows.map((r) => r.bdcName))].sort();
          const quarters = [...new Set(rows.map((r) => r.periodEnd))].sort().reverse();
          const types = [...new Set(rows.map((r) => r.formType))].sort();
          const shown = rows.filter((r) => (!lender || r.bdcName === lender) && (!quarter || r.periodEnd === quarter) && (!formType || r.formType === formType));
          const sel = selected ?? shown[0] ?? null;

          // Coverage matrix: a cell is present only if that exact lender/quarter pair exists in the
          // real E10 list. There is no "issue" state in the data, only present or absent, so a
          // missing cell reads as not yet filed (amber), never a fabricated red "problem".
          const quartersAsc = quarters.slice().reverse();
          const hasFiling = (name, q) => rows.some((r) => r.bdcName === name && r.periodEnd === q);
          const latest = rows.slice().sort((a, b) => (a.periodEnd < b.periodEnd ? 1 : a.periodEnd > b.periodEnd ? -1 : a.bdcName.localeCompare(b.bdcName))).slice(0, 5);

          return (
            <div className="space-y-5">
              <div className="flex flex-wrap items-center gap-3">
                <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>Financial reports used to build the comparison data</p>
                <span className="ml-auto rounded-full px-2.5 py-1 text-xs font-semibold" style={{ background: "var(--color-brand-light)", color: "var(--color-brand-dark)" }}>{rows.length} filings</span>
              </div>

              <div className="flex flex-wrap gap-2">
                <select value={lender} onChange={(e) => setLender(e.target.value)} className="rounded-xl border px-3 py-1.5 text-sm" style={inputStyle}>
                  <option value="">All lenders</option>
                  {lenders.map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
                <select value={quarter} onChange={(e) => setQuarter(e.target.value)} className="rounded-xl border px-3 py-1.5 text-sm" style={inputStyle}>
                  <option value="">All quarters</option>
                  {quarters.map((q) => <option key={q} value={q}>{quarterLabel(q)}</option>)}
                </select>
                <select value={formType} onChange={(e) => setFormType(e.target.value)} className="rounded-xl border px-3 py-1.5 text-sm" style={inputStyle}>
                  <option value="">All filing types</option>
                  {types.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>

              <Card compact id="filings-table">
                <CardLabel>Filings</CardLabel>
                {shown.length === 0 ? (
                  <EmptyState>No filings match this filter.</EmptyState>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-sm">
                      <thead>
                        <tr style={{ color: "var(--color-text-secondary)" }}>
                          <th className="py-1.5 pr-4 font-medium">Lender</th>
                          <th className="py-1.5 pr-4 font-medium">Quarter</th>
                          <th className="py-1.5 pr-4 font-medium">Filing</th>
                          <th className="py-1.5 pr-2 font-medium">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {shown.map((r) => (
                          <tr
                            key={r.sourceUrl}
                            onClick={() => setSelected(r)}
                            className="table-row-hover cursor-pointer border-t transition-colors"
                            style={{ borderColor: "var(--color-border)", background: sel === r ? "var(--color-brand-faint)" : undefined }}
                          >
                            <td className="py-2 pr-4" style={{ color: "var(--color-text)" }}>{r.bdcName}<PeriodTag periodEnd={r.periodEnd} measured={overview?.measuredPeriodEnd} /></td>
                            <td className="py-2 pr-4" style={{ color: "var(--color-text-secondary)" }}>{quarterLabel(r.periodEnd)}</td>
                            <td className="py-2 pr-4" style={{ color: "var(--color-text-secondary)" }}>{r.formType}</td>
                            <td className="py-2 pr-2"><StatusDot flag="AGREEMENT" label="Processed" /> <span className="text-xs" style={{ color: "var(--color-text-secondary)" }}>Processed</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>

              <Card compact>
                <CardLabel>Filings coverage</CardLabel>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr style={{ color: "var(--color-text-secondary)" }}>
                        <th className="py-1.5 pr-4 font-medium">Lender</th>
                        {quartersAsc.map((q) => (
                          <th key={q} className="px-3 py-1.5 text-center font-medium">{quarterLabel(q)}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {lenders.map((name) => (
                        <tr key={name} className="border-t" style={{ borderColor: "var(--color-border)" }}>
                          <td className="py-2 pr-4" style={{ color: "var(--color-text)" }}>{name}</td>
                          {quartersAsc.map((q) => (
                            <td key={q} className="px-3 py-2 text-center">
                              {hasFiling(name, q) ? (
                                <span style={{ color: "var(--color-chart-green)" }} aria-label="Filed and processed" title="Filed and processed">&#10003;</span>
                              ) : (
                                <span style={{ color: "var(--color-review)" }} aria-label="Not yet filed" title="Not yet filed">&#9675;</span>
                              )}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="border-t" style={{ borderColor: "var(--color-border)" }}>
                        <td className="py-2 pr-4 text-xs font-semibold" style={{ color: "var(--color-text-muted)" }}>Complete</td>
                        {quartersAsc.map((q) => {
                          const n = lenders.filter((name) => hasFiling(name, q)).length;
                          return (
                            <td key={q} className="px-3 py-2 text-center text-xs" style={{ color: n === lenders.length ? "var(--color-chart-green)" : "var(--color-review)" }}>
                              {n} / {lenders.length}
                            </td>
                          );
                        })}
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </Card>

              <Card compact>
                <CardLabel>Latest filings</CardLabel>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr style={{ color: "var(--color-text-secondary)" }}>
                        <th className="py-1.5 pr-4 font-medium">Date</th>
                        <th className="py-1.5 pr-4 font-medium">Lender</th>
                        <th className="py-1.5 pr-4 font-medium">Type</th>
                        <th className="py-1.5 pr-2 font-medium">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {latest.map((r) => (
                        <tr key={r.sourceUrl} className="border-t" style={{ borderColor: "var(--color-border)" }}>
                          <td className="py-2 pr-4" style={{ color: "var(--color-text)" }}>{r.periodEnd}</td>
                          <td className="py-2 pr-4" style={{ color: "var(--color-text)" }}>{r.bdcName}</td>
                          <td className="py-2 pr-4" style={{ color: "var(--color-text-secondary)" }}>{r.formType}</td>
                          <td className="py-2 pr-2"><StatusDot flag="AGREEMENT" label="Processed" /> <span className="text-xs" style={{ color: "var(--color-text-secondary)" }}>Processed</span></td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div className="mt-3 text-right">
                  <a href="#filings-table" className="text-sm font-medium hover:underline" style={{ color: "var(--color-brand-dark)" }}>View all filings &rarr;</a>
                </div>
              </Card>

              {sel && (
                <Card compact>
                  <CardLabel>Selected filing</CardLabel>
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <p className="font-semibold" style={{ color: "var(--color-text)" }}>{sel.bdcName}</p>
                    <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>{quarterLabel(sel.periodEnd)}</p>
                  </div>
                  <p className="mt-1 text-sm" style={{ color: "var(--color-text-secondary)" }}>
                    Filed: {sel.periodEnd} &nbsp;&middot;&nbsp; Type: {sel.formType} &nbsp;&middot;&nbsp; Status: <StatusDot flag="AGREEMENT" label="Processed" /> Processed
                  </p>
                  <p className="mt-3 text-sm" style={{ color: "var(--color-text)" }}>
                    <span className="font-semibold">{sel.holdingsCount}</span> <span style={{ color: "var(--color-text-secondary)" }}>holdings reported</span>
                  </p>
                  <p className="mt-3"><SourceLink url={sel.sourceUrl}>View SEC filing</SourceLink></p>
                </Card>
              )}
            </div>
          );
        }}
      </Load>
    </>
  );
}

