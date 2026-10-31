import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { ApiFailure, getJson } from "./api.js";
import { useShared } from "./App.jsx";
import {
  Card,
  CardLabel,
  ClickableDivergenceBar,
  DivergenceDonut,
  EmptyState,
  ErrorState,
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

// ------------------------------------------------------------------ 4.2 Borrowers
export function BorrowersPage() {
  const [params, setParams] = useSearchParams();
  const [text, setText] = useState(params.get("search") ?? "");
  const urlSearch = params.get("search") ?? "";
  useEffect(() => setText(urlSearch), [urlSearch]);
  const q = useDebounced(text.trim());
  const f = useFetch(() => getJson("/api/borrowers", { search: q || undefined }), [q]);
  const { overview } = useShared();
  return (
    <>
      <PageTitle>Borrowers</PageTitle>
      <input
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          setParams(e.target.value.trim() ? { search: e.target.value.trim() } : {}, { replace: true });
        }}
        placeholder="Search borrower"
        aria-label="Search borrower"
        maxLength={200}
        className={`mb-5 max-w-md ${inputClass}`}
        style={inputStyle}
      />
      <Load f={f}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState>No borrowers match this search.</EmptyState>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {rows.map((b) => (
                <Card key={b.canonicalBorrowerId} to={`/borrowers/${b.canonicalBorrowerId}`}>
                  <p className="font-semibold uppercase" style={{ color: "var(--color-text)" }}>{b.canonicalName}</p>
                  <p className="mt-1 text-sm" style={{ color: "var(--color-text-secondary)" }}>{b.periodEnd}<PeriodTag periodEnd={b.periodEnd} measured={overview?.measuredPeriodEnd} /></p>
                  <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>{b.lenderCount} {b.lenderCount === 1 ? "Lender" : "Lenders"}</p>
                  <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>{b.facilityCount} {b.facilityCount === 1 ? "Facility" : "Facilities"}</p>
                  <p className="mt-2 text-sm font-medium" style={{ color: "var(--color-brand-dark)" }}>View borrower &rarr;</p>
                </Card>
              ))}
            </div>
          )
        }
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

// ------------------------------------------------------------------ 4.8 Filings
export function FilingsPage() {
  const f = useFetch(() => getJson("/api/filings"), []);
  const [filter, setFilter] = useState("");
  const { overview } = useShared();
  return (
    <>
      <PageTitle sub="The source documents behind the monitor">SEC filings</PageTitle>
      <input
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Filter filings"
        aria-label="Filter filings"
        maxLength={200}
        className={`mb-5 max-w-md ${inputClass}`}
        style={inputStyle}
      />
      <Load f={f}>
        {(rows) => {
          const t = filter.trim().toLowerCase();
          const shown = rows.filter((r) => !t || `${r.bdcName} ${r.formType} ${r.periodEnd}`.toLowerCase().includes(t));
          return shown.length === 0 ? (
            <EmptyState>No filings match this filter.</EmptyState>
          ) : (
            <div className="space-y-4">
              {shown.map((r) => (
                <Card key={r.sourceUrl}>
                  <p className="font-semibold" style={{ color: "var(--color-text)" }}>{r.bdcName}</p>
                  <p className="mt-1 text-sm" style={{ color: "var(--color-text-secondary)" }}>{r.formType}, period end {r.periodEnd}<PeriodTag periodEnd={r.periodEnd} measured={overview?.measuredPeriodEnd} /></p>
                  <p className="mt-1 text-sm" style={{ color: "var(--color-text-secondary)" }}>Holdings: {r.holdingsCount} &nbsp; <SourceLink url={r.sourceUrl}>View SEC filing</SourceLink></p>
                </Card>
              ))}
            </div>
          );
        }}
      </Load>
    </>
  );
}

