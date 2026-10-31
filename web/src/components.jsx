import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { ApiFailure } from "./api.js";
import { FLAG_TEXT, NOT_YET, PERSISTENCE_TEXT, SIGNAL_TEXT, fixed, pct, usd } from "./format.js";

export function useFetch(load, deps) {
  const [s, setS] = useState({ state: "loading" });
  const [tick, setTick] = useState(0);
  const retry = useCallback(() => setTick((t) => t + 1), []);
  useEffect(() => {
    let live = true;
    setS({ state: "loading" });
    load().then(
      (data) => live && setS({ state: "ready", data }),
      (error) => live && setS({ state: "error", error, retry }),
    );
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick]);
  return s;
}

export function Skeleton() {
  return (
    <div className="animate-pulse space-y-3" aria-busy="true" aria-label="Loading">
      {[0, 1, 2].map((i) => <div key={i} className="h-16 rounded-2xl bg-[var(--color-border)]" />)}
    </div>
  );
}

export function ErrorState({ error, retry }) {
  return (
    <div role="alert" className="rounded-2xl border p-5" style={{ borderColor: "var(--color-flagged)", background: "var(--color-flagged-light)" }}>
      <p className="font-semibold" style={{ color: "var(--color-text)" }}>Something went wrong.</p>
      <p className="break-words text-sm" style={{ color: "var(--color-text-secondary)" }}>{error.message}</p>
      <button className="btn-secondary mt-3" onClick={retry}>Retry</button>
    </div>
  );
}

export function EmptyState({ children }) {
  return (
    <p className="rounded-2xl border border-dashed p-6 text-center text-sm" style={{ borderColor: "var(--color-border)", color: "var(--color-text-secondary)" }}>
      {children}
    </p>
  );
}

// Renders the four page states for one fetch.
export function Load({ f, children }) {
  if (f.state === "loading") return <Skeleton />;
  if (f.state === "error") return <ErrorState error={f.error} retry={f.retry} />;
  return <>{children(f.data)}</>;
}

// ------------------------------------------------------------------ cards and labels

// Status colour tokens shared by every pill, bar and chip in the app. Keyed by the Flag enum.
const FLAG_STATUS = {
  AGREEMENT: { fg: "var(--color-brand-dark)", bg: "var(--color-brand-light)", dot: "var(--color-brand)" },
  MILD: { fg: "var(--color-review)", bg: "var(--color-review-light)", dot: "var(--color-review)" },
  FLAGGED: { fg: "var(--color-flagged)", bg: "var(--color-flagged-light)", dot: "var(--color-flagged)" },
};

export function Card({ children, to, className = "" }) {
  const base = `card-shadow rounded-[var(--radius-card)] border p-5 ${className}`;
  const style = { background: "var(--color-surface)", borderColor: "var(--color-border)" };
  if (!to) return <div className={base} style={style}>{children}</div>;
  return (
    <Link to={to} className={`block transition-colors hover:bg-[var(--color-brand-light)]/40 ${base}`} style={style}>
      {children}
    </Link>
  );
}

// A small all-caps section label, used as the header of a card in place of a generic heading.
export function CardLabel({ children }) {
  return <p className="mb-3 text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-text-secondary)" }}>{children}</p>;
}

export function StatCard({ label, value, to, note }) {
  return (
    <Card to={to}>
      <p className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--color-text-secondary)" }}>{label}</p>
      <p className="mt-2 text-[28px] font-bold leading-none" style={{ color: "var(--color-text)" }}>{value}</p>
      {note && <p className="mt-1 text-sm" style={{ color: "var(--color-text-secondary)" }}>{note}</p>}
    </Card>
  );
}

export function PeriodTag({ periodEnd, measured }) {
  return measured && periodEnd !== measured ? (
    <span className="ml-2 rounded-full border px-2 py-0.5 text-xs" style={{ borderColor: "var(--color-border)", color: "var(--color-text-secondary)" }}>
      Outside measured quarter
    </span>
  ) : null;
}

export function SourceLink({ url, children = "View filing" }) {
  return (
    <a className="font-medium underline-offset-2 hover:underline" style={{ color: "var(--color-brand-dark)" }} href={url} target="_blank" rel="noreferrer">
      {children}
    </a>
  );
}

// A status pill: a dot plus text, tinted with the flag's colour. Used for divergence flags everywhere.
export function StatusPill({ flag }) {
  const s = FLAG_STATUS[flag] ?? { fg: "var(--color-text-secondary)", bg: "var(--color-border)", dot: "var(--color-text-secondary)" };
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold" style={{ color: s.fg, background: s.bg }}>
      <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ background: s.dot }} />
      {FLAG_TEXT[flag] ?? flag}
    </span>
  );
}

export function Banner({ flag, points }) {
  const s = FLAG_STATUS[flag] ?? { fg: "var(--color-text)", bg: "var(--color-border)" };
  return (
    <div className="rounded-[var(--radius-card)] border p-5" style={{ borderColor: "var(--color-border)", background: s.bg }} role="status">
      <p className="text-xl font-bold" style={{ color: s.fg }}>{FLAG_TEXT[flag] ?? flag}</p>
      <p className="text-sm" style={{ color: "var(--color-text-secondary)" }}>{fixed(points, 2)} points of fair value, highest minus lowest lender</p>
    </div>
  );
}

export function ExposureTag({ exposureUsd }) {
  return (
    <span>
      <span style={{ color: "var(--color-text)" }}>Exposure {usd(exposureUsd)}</span>
      <span className="block text-xs" style={{ color: "var(--color-text-muted)" }}>Ranking key, not an estimate of loss.</span>
    </span>
  );
}

export function SignalChip({ code }) {
  return (
    <span className="mr-1 inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium" style={{ borderColor: "var(--color-border)", color: "var(--color-text-secondary)" }}>
      {SIGNAL_TEXT[code] ?? code}
    </span>
  );
}

export function PersistenceTag({ persistence }) {
  return (
    <span className="rounded-full border px-2.5 py-0.5 text-xs font-medium" style={{ borderColor: "var(--color-border)", color: "var(--color-text-secondary)" }}>
      {persistence === null ? NOT_YET : PERSISTENCE_TEXT[persistence]}
    </span>
  );
}

// ------------------------------------------------------------------ chart primitives (real data only)

// Horizontal bars for the three divergence flags, counts supplied by the caller (overview.divergenceSplit).
export function DivergenceSplitChart({ agreement, mild, flagged }) {
  const rows = [
    ["AGREEMENT", agreement],
    ["MILD", mild],
    ["FLAGGED", flagged],
  ];
  const max = Math.max(1, agreement, mild, flagged);
  return (
    <div className="space-y-3">
      {rows.map(([flag, n]) => {
        const s = FLAG_STATUS[flag];
        return (
          <div key={flag} className="flex items-center gap-3">
            <span className="w-20 shrink-0 text-xs font-medium" style={{ color: "var(--color-text-secondary)" }}>{FLAG_TEXT[flag]}</span>
            <div className="h-2.5 flex-1 overflow-hidden rounded-full" style={{ background: "var(--color-border)" }}>
              <div className="h-full rounded-full" style={{ width: `${(n / max) * 100}%`, background: s.dot }} />
            </div>
            <span className="w-8 shrink-0 text-right text-sm font-semibold" style={{ color: "var(--color-text)" }}>{n}</span>
          </div>
        );
      })}
    </div>
  );
}

// A ranked horizontal-bar list of named rows against a shared total, e.g. flagged exposure by borrower.
export function RankedShareList({ rows, total }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <div className="space-y-3">
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-3">
          <span className="w-28 shrink-0 truncate text-sm font-medium" style={{ color: "var(--color-text)" }}>{r.label}</span>
          <div className="h-2 flex-1 overflow-hidden rounded-full" style={{ background: "var(--color-border)" }}>
            <div className="h-full rounded-full" style={{ width: `${(r.value / max) * 100}%`, background: "var(--color-flagged)" }} />
          </div>
          <span className="w-10 shrink-0 text-right text-xs font-semibold" style={{ color: "var(--color-text-secondary)" }}>
            {total ? `${((r.value / total) * 100).toFixed(0)}%` : r.value}
          </span>
        </div>
      ))}
    </div>
  );
}

// ------------------------------------------------------------------ metric values
export function ci(c, interval = "95% interval") {
  return c ? `${pct(c.value)} (${interval} ${pct(c.low)} to ${pct(c.high)}, n ${c.n})` : NOT_YET;
}

// A Range with its three UNSURE treatments. Sorted by value so the range always reads low to high.
// kind "recall" labels the two UNSURE treatments by what they do, because counting UNSURE as no match raises recall (no worst or best wording).
// weighted marks a band weighted figure: its interval is a bootstrap over bands, which has zero width when every sampled AUTO label is a match.
export function RangeStat({ title, range, kind = "precision", weighted = false }) {
  if (!range) return <Card><p className="font-semibold">{title}</p><p>{NOT_YET}</p></Card>;
  const lines = [
    ["UNSURE excluded (headline)", range.unsureExcluded],
    [kind === "recall" ? "UNSURE counted as no match" : "Worst case, UNSURE counted as no match", range.unsureAsNoMatch],
    [kind === "recall" ? "UNSURE counted as match" : "Best case, UNSURE counted as match", range.unsureAsMatch],
  ];
  const interval = weighted ? "bootstrap, weighted, 95% interval" : "95% interval";
  const known = lines.map(([, c]) => c).filter((c) => c !== null).sort((a, b) => a.value - b.value);
  return (
    <Card>
      <p className="font-semibold">{title}</p>
      {known.length >= 2 && <p className="text-sm">Range across treatments: {pct(known[0].value)} to {pct(known[known.length - 1].value)}</p>}
      <ul className="mt-1 space-y-1">
        {lines.map(([label, c]) => (
          <li key={label}><span className="font-medium">{label}:</span> {ci(c, interval)}</li>
        ))}
      </ul>
      {weighted && <p className="mt-1 text-xs">The bootstrap interval has zero width when every sampled AUTO label is a match.</p>}
    </Card>
  );
}

export function BandTable({ bands }) {
  const name = (n) => ({ AUTO: "AUTO", REVIEW: "REVIEW", JUST_BELOW: "Just below", LOW: "Low" })[n] ?? n;
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr><th className="p-1">Band</th><th className="p-1">Band size</th><th className="p-1">Sample</th><th className="p-1">Match</th><th className="p-1">No match</th><th className="p-1">Unsure</th><th className="p-1">Match rate</th></tr>
        </thead>
        <tbody>
          {bands.map((b) => (
            <tr key={b.name} className="border-t">
              <td className="p-1">{name(b.name)}</td>
              <td className="p-1">{b.bandSize}</td>
              <td className="p-1">{b.sampleSize}{b.labeledInFull ? " (all)" : ""}</td>
              <td className="p-1">{b.counts.match}</td>
              <td className="p-1">{b.counts.noMatch}</td>
              <td className="p-1">{b.counts.unsure}</td>
              <td className="p-1">
                {b.matchRate ? ci(b.matchRate.unsureExcluded) : b.sampleSize === 0 ? "Not sampled" : `Counts only: ${b.counts.match} of ${b.sampleSize} matched`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ------------------------------------------------------------------ comparison pieces
function range(values) {
  return [Math.min(...values), Math.max(...values)];
}

// One dot per lender on a fair value / par axis, inline SVG, no chart library.
export function DotPlot({ rows }) {
  const [lo, hi] = range(rows.map((r) => r.value));
  const pad = Math.max((hi - lo) * 0.15, 0.5);
  const a = lo - pad, b = hi + pad;
  const x = (v) => 20 + ((v - a) / (b - a)) * 560;
  return (
    <svg viewBox="0 0 600 60" role="img" aria-label="Fair value as a percent of par, one dot per lender" className="w-full">
      <line x1="20" y1="30" x2="580" y2="30" stroke="currentColor" />
      {rows.map((r, i) => (
        <g key={r.label}>
          <circle cx={x(r.value)} cy="30" r="6" fill="currentColor" />
          <text x={x(r.value)} y={i % 2 ? 54 : 14} fontSize="11" textAnchor="middle" fill="currentColor">{r.label} {r.value.toFixed(2)}</text>
        </g>
      ))}
    </svg>
  );
}

// Prior to current marks, one pair of dots per lender, inline SVG. A missing prior mark is drawn as text, never as a dot.
export function HistoryStrip({ rows, persistence }) {
  const vals = rows.flatMap((r) => (r.prior === null ? [r.current] : [r.prior, r.current]));
  const [lo, hi] = range(vals);
  const pad = Math.max((hi - lo) * 0.15, 0.5);
  const a = lo - pad, b = hi + pad;
  const x = (v) => 150 + ((v - a) / (b - a)) * 430;
  return (
    <div>
      <p className="mb-1">Persistence: <PersistenceTag persistence={persistence} /></p>
      <svg viewBox={`0 0 600 ${rows.length * 28 + 8}`} role="img" aria-label="Prior quarter mark to current mark for each lender" className="w-full">
        {rows.map((r, i) => (
          <g key={r.bdcName}>
            <text x="0" y={i * 28 + 22} fontSize="11" fill="currentColor">{r.bdcName.slice(0, 22)}</text>
            {r.prior !== null && <line x1={x(r.prior)} y1={i * 28 + 18} x2={x(r.current)} y2={i * 28 + 18} stroke="currentColor" />}
            {r.prior !== null && <circle cx={x(r.prior)} cy={i * 28 + 18} r="4" fill="none" stroke="currentColor" strokeWidth="2" />}
            <circle cx={x(r.current)} cy={i * 28 + 18} r="5" fill="currentColor" />
            <text x="590" y={i * 28 + 22} fontSize="10" textAnchor="end" fill="currentColor">{r.prior === null ? "No linked prior mark" : `${r.prior.toFixed(2)} to ${r.current.toFixed(2)}`}</text>
          </g>
        ))}
      </svg>
      <p className="text-xs">Open dot: prior quarter. Filled dot: this quarter. Two quarters are not a trend.</p>
    </div>
  );
}

const COLS = [
  { head: "Spread", cell: (r) => (r.spreadBps === null ? null : fixed(r.spreadBps, 0) + " bps"), dossier: false },
  { head: "FV % of par", cell: (r) => fixed(r.fairValuePctPar, 2), dossier: false },
  { head: "Cost % of par", cell: (r) => (r.costPctPar === null ? null : fixed(r.costPctPar, 2)), dossier: true },
  { head: "FV % of cost", cell: (r) => (r.fvPctCost === null ? null : fixed(r.fvPctCost, 2)), dossier: true },
  { head: "Floor", cell: (r) => (r.floorBps === null ? null : fixed(r.floorBps, 0) + " bps"), dossier: true },
  { head: "PIK", cell: (r) => (r.pikBps === null ? null : fixed(r.pikBps, 0) + " bps"), dossier: true },
  { head: "Maturity", cell: (r) => r.maturityDate, dossier: true },
  { head: "Non accrual", cell: (r) => (r.nonAccrual === null ? null : r.nonAccrual ? "Yes" : "No"), dossier: true },
];

// The lender table with the dossier columns. A null dossier cell reads "Not disclosed". A column whose disclosed values differ is marked with text.
export function EvidenceTable({ rows }) {
  const differs = COLS.map((c) => new Set(rows.map(c.cell).filter((v) => v !== null)).size > 1);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr>
            <th className="p-1">BDC</th>
            {COLS.map((c, i) => <th key={c.head} className="p-1">{c.head}{differs[i] && <span className="block text-xs font-normal">differs</span>}</th>)}
            <th className="p-1">Principal</th><th className="p-1">Source</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.bdcName + r.sourceUrl} className="border-t">
              <td className="p-1 font-medium">{r.bdcName}</td>
              {COLS.map((c, i) => {
                const v = c.cell(r);
                return <td key={c.head} className={`p-1 ${differs[i] ? "font-semibold" : ""}`}>{v === null ? (c.dossier ? "Not disclosed" : NOT_YET) : v}</td>;
              })}
              <td className="p-1">{usd(r.principal)}</td>
              <td className="p-1"><SourceLink url={r.sourceUrl} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function PageTitle({ children, sub }) {
  return (
    <div className="mb-6">
      <h1 className="text-[28px] font-bold leading-tight" style={{ color: "var(--color-text)" }}>{children}</h1>
      {sub && <p className="mt-1 text-sm" style={{ color: "var(--color-text-secondary)" }}>{sub}</p>}
    </div>
  );
}

// Small shared control styles, reused by every page's search/filter inputs and buttons.
export const inputClass = "w-full rounded-xl border px-3.5 py-2 text-sm outline-none transition-colors placeholder:text-[var(--color-text-muted)] focus:border-[var(--color-brand)]";
export const inputStyle = { background: "var(--color-surface)", borderColor: "var(--color-border)", color: "var(--color-text)" };
