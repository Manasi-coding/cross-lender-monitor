import { useEffect, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { ApiFailure, getJson } from "./api";
import { useShared } from "./App";
import { Card, EmptyState, Load, PageTitle, PeriodTag, SourceLink, StatCard, useFetch } from "./components";
import { NOT_YET, typeName, usd } from "./format";
import type { BorrowerFacilities, BorrowerRow, Filing } from "./types";

export function useDebounced<T>(value: T, ms = 300): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

const share = (n: number, total: number) => (total === 0 ? NOT_YET : `${((n / total) * 100).toFixed(1)}%`);

// ------------------------------------------------------------------ 4.1 Overview
export function OverviewPage() {
  const { overview: o } = useShared();
  return (
    <>
      <PageTitle sub={o ? `Measured quarter: ${o.measuredPeriodEnd}` : undefined}>Overview</PageTitle>
      {!o ? (
        <p>{NOT_YET}</p>
      ) : (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard label="BDCs" value={o.bdcCount} to="/filings" />
            <StatCard label="Facilities" value={o.facilityCount} to="/facilities" />
            <StatCard label="Pending reviews" value={o.pendingReviewCount} to="/review" />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Card to="/borrowers"><p className="font-semibold">Browse borrowers</p></Card>
            <Card to="/review"><p className="font-semibold">Review queue</p></Card>
          </div>
          <Card to="/metrics">
            <p className="font-semibold">Valuation divergence</p>
            {o.divergenceSplit ? (
              (() => {
                const s = o.divergenceSplit;
                const t = s.agreement + s.mild + s.flagged;
                return <p>Agreement {s.agreement} ({share(s.agreement, t)}). Mild {s.mild} ({share(s.mild, t)}). Flagged {s.flagged} ({share(s.flagged, t)}).</p>;
              })()
            ) : (
              <p>{NOT_YET}</p>
            )}
          </Card>
          <Card to="/facilities">
            <p className="font-semibold">Flagged exposure</p>
            <p className="text-xl">{usd(o.flaggedExposureUsd)}</p>
            <p className="text-sm">Ranking key, not an estimate of loss.</p>
          </Card>
        </div>
      )}
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
  const f = useFetch(() => getJson<BorrowerRow[]>("/api/borrowers", { search: q || undefined }), [q]);
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
        className="mb-4 w-full max-w-md rounded border px-3 py-1"
      />
      <Load f={f}>
        {(rows) =>
          rows.length === 0 ? (
            <EmptyState>No borrowers match this search.</EmptyState>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {rows.map((b) => (
                <Card key={b.canonicalBorrowerId} to={`/borrowers/${b.canonicalBorrowerId}`}>
                  <p className="font-bold uppercase">{b.canonicalName}</p>
                  <p>{b.periodEnd}<PeriodTag periodEnd={b.periodEnd} measured={overview?.measuredPeriodEnd} /></p>
                  <p>{b.lenderCount} {b.lenderCount === 1 ? "Lender" : "Lenders"}</p>
                  <p>{b.facilityCount} {b.facilityCount === 1 ? "Facility" : "Facilities"}</p>
                  <p className="underline">View borrower</p>
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
  const f = useFetch(() => getJson<BorrowerFacilities>(`/api/borrowers/${encodeURIComponent(id)}/facilities`), [id]);
  const { overview } = useShared();
  if (f.state === "error" && f.error instanceof ApiFailure && f.error.status === 404) {
    return (
      <>
        <Link to="/borrowers" className="underline">Borrowers</Link>
        <EmptyState>This borrower is not in the current build.</EmptyState>
      </>
    );
  }
  return (
    <>
      <Link to="/borrowers" className="underline">Back to borrowers</Link>
      <Load f={f}>
        {(b) => (
          <>
            <PageTitle sub={<>{b.lenderCount} lenders, {b.facilityCount} facilities. Period end {b.periodEnd}<PeriodTag periodEnd={b.periodEnd} measured={overview?.measuredPeriodEnd} /></>}>
              <span className="uppercase">{b.canonicalName}</span>
            </PageTitle>
            <div className="space-y-4">
              {b.facilities.map((x) => (
                <Card key={x.facilityId} to={`/facilities/${x.facilityId}`}>
                  <p className="font-semibold">{typeName(x.instrumentType)}</p>
                  <p>{x.referenceRate ?? "Reference rate not disclosed"}, maturity bucket {x.maturityBucket ?? "Not disclosed"}</p>
                  <p>{x.lenderCount} lenders</p>
                  <p className="underline">View comparison</p>
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
  const f = useFetch(() => getJson<Filing[]>("/api/filings"), []);
  const [filter, setFilter] = useState("");
  const { overview } = useShared();
  return (
    <>
      <PageTitle>SEC filings</PageTitle>
      <input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder="Filter filings" aria-label="Filter filings" maxLength={200} className="mb-4 w-full max-w-md rounded border px-3 py-1" />
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
                  <p className="font-semibold">{r.bdcName}</p>
                  <p>{r.formType}, period end {r.periodEnd}<PeriodTag periodEnd={r.periodEnd} measured={overview?.measuredPeriodEnd} /></p>
                  <p>Holdings: {r.holdingsCount} <SourceLink url={r.sourceUrl}>View SEC filing</SourceLink></p>
                </Card>
              ))}
            </div>
          );
        }}
      </Load>
    </>
  );
}

