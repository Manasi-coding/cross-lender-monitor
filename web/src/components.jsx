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

// Minimal hand-drawn icon set, 20x20, stroke-based, one colour (currentColor). No icon library dependency.
const ICON_PATHS = {
  layers: "M10 2 2 6l8 4 8-4-8-4ZM2 10l8 4 8-4M2 14l8 4 8-4",
  flag: "M4 17V3m0 2h11l-2.5 3L15 11H4",
  alert: "M10 2 2 17h16L10 2ZM10 8v4m0 3h.01",
  check: "M3 10.5 8 15l9-10.5",
  chart: "M3 17V8m5 9V3m5 14v-6m5 6V6",
  search: "M9 16a7 7 0 1 0 0-14 7 7 0 0 0 0 14ZM18 18l-4-4",
  doc: "M5 2h7l4 4v12H5V2Zm7 0v4h4",
  grid: "M3 3h6v6H3V3Zm8 0h6v6h-6V3ZM3 11h6v6H3v-6Zm8 0h6v6h-6v-6Z",
};

export function Icon({ name, size = 18, className = "" }) {
  const d = ICON_PATHS[name];
  if (!d) return null;
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

// Tone drives the tinted icon badge colour. "neutral" uses the brand colour at low intensity.
const TONE = {
  neutral: { bg: "var(--color-brand-light)", fg: "var(--color-brand-dark)" },
  brand: { bg: "var(--color-brand-light)", fg: "var(--color-brand-dark)" },
  review: { bg: "var(--color-review-light)", fg: "var(--color-review)" },
  flagged: { bg: "var(--color-flagged-light)", fg: "var(--color-flagged)" },
};

export function StatCard({ label, value, to, note, tone = "neutral", icon }) {
  const t = TONE[tone] ?? TONE.neutral;
  return (
    <Card to={to}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--color-text-secondary)" }}>{label}</p>
          <p className="mt-2 text-[28px] font-bold leading-none" style={{ color: "var(--color-text)" }}>{value}</p>
          {note && <p className="mt-1.5 text-sm" style={{ color: "var(--color-text-secondary)" }}>{note}</p>}
        </div>
        {icon && (
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full" style={{ background: t.bg, color: t.fg }}>
            <Icon name={icon} />
          </span>
        )}
      </div>
    </Card>
  );
}

// A gradient banner card for the page's headline figure, with pill CTAs. Content is caller-supplied real data only.
export function HeroCard({ eyebrow, title, subtitle, actions }) {
  return (
    <div className="gradient-hero card-shadow rounded-[var(--radius-card)] p-6 text-white sm:p-7">
      {eyebrow && <p className="text-xs font-semibold uppercase tracking-wide text-white/75">{eyebrow}</p>}
      <p className="mt-2 text-2xl font-bold leading-snug sm:text-[28px]">{title}</p>
      {subtitle && <p className="mt-2 max-w-xl text-sm text-white/85">{subtitle}</p>}
      {actions && <div className="mt-5 flex flex-wrap gap-2.5">{actions}</div>}
    </div>
  );
}

export function HeroLink({ to, children }) {
  return (
    <Link
      to={to}
      className="rounded-xl bg-white/15 px-4 py-2 text-sm font-semibold text-white backdrop-blur-sm transition-colors hover:bg-white/25"
    >
      {children}
    </Link>
  );
}

// A small donut built from the three divergence flags, same colours as every other status element.
export function DivergenceDonut({ agreement, mild, flagged }) {
  const total = agreement + mild + flagged;
  const r = 15.9155;
  const c = 2 * Math.PI * r;
  const segs = [
    ["AGREEMENT", agreement, "var(--color-brand)"],
    ["MILD", mild, "var(--color-review)"],
    ["FLAGGED", flagged, "var(--color-flagged)"],
  ];
  let offset = 0;
  return (
    <div className="flex items-center gap-5">
      <svg viewBox="0 0 36 36" className="h-28 w-28 shrink-0 -rotate-90" role="img" aria-label="Share of facilities by agreement status">
        <circle cx="18" cy="18" r={r} fill="none" stroke="var(--color-border)" strokeWidth="4" />
        {total > 0 &&
          segs.map(([name, n, color]) => {
            if (n === 0) return null;
            const frac = n / total;
            const dash = `${frac * c} ${c - frac * c}`;
            const el = <circle key={name} cx="18" cy="18" r={r} fill="none" stroke={color} strokeWidth="4" strokeDasharray={dash} strokeDashoffset={-offset} strokeLinecap="butt" />;
            offset += frac * c;
            return el;
          })}
      </svg>
      <div className="space-y-2 text-sm">
        {segs.map(([name, n, color]) => (
          <div key={name} className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: color }} />
            <span style={{ color: "var(--color-text-secondary)" }}>{FLAG_TEXT[name]}</span>
            <span className="font-semibold" style={{ color: "var(--color-text)" }}>{n}</span>
          </div>
        ))}
      </div>
    </div>
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
