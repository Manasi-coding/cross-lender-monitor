import { Fragment, useCallback, useEffect, useState } from "react";
import { Link } from "react-router";
import { ApiFailure } from "./api.js";
import { FLAG_TEXT, NOT_DISCLOSED, NOT_YET, PERSISTENCE_TEXT, SIGNAL_TEXT, fixed, pct, usd } from "./format.js";

// Fetches on mount/dep change and again whenever the tab regains focus, so a page left open shows
// what the API has now rather than a stale snapshot. A fetch already in flight is not duplicated.
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
  useEffect(() => {
    const onFocus = () => retry();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [retry]);
  return s;
}

// Animates a number from 0 to a real, already-known target over a short duration, using
// requestAnimationFrame. The last frame always sets the exact target, so the displayed value
// never lands on anything other than what the API returned.
export function useCountUp(target, durationMs = 700) {
  const [value, setValue] = useState(() => (Number.isFinite(target) ? 0 : target));
  useEffect(() => {
    if (!Number.isFinite(target)) {
      setValue(target);
      return;
    }
    let raf;
    const start = performance.now();
    const from = 0;
    const tick = (now) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - (1 - t) * (1 - t);
      setValue(from + (target - from) * eased);
      if (t < 1) raf = requestAnimationFrame(tick);
      else setValue(target);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, durationMs]);
  return value;
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
  const style = { background: "var(--color-surface)", borderColor: "var(--color-border-strong)" };
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

// value is shown as-is. Pass countTo (a real number already in hand) plus format to animate the
// digits up to that same number on mount; the final frame always renders format(countTo) exactly.
export function StatCard({ label, value, countTo, format, to, note, tone = "neutral", icon }) {
  const t = TONE[tone] ?? TONE.neutral;
  const animated = useCountUp(countTo ?? NaN);
  const shown = Number.isFinite(countTo) ? format(animated) : value;
  return (
    <Card to={to}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--color-text-secondary)" }}>{label}</p>
          <p className="mt-2 text-[28px] font-bold leading-none tabular-nums" style={{ color: "var(--color-text)" }}>{shown}</p>
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

// A solid, single-colour banner card for the page's headline figure, with pill CTAs. Content is caller-supplied real data only.
export function HeroCard({ eyebrow, title, subtitle, actions }) {
  return (
    <div className="hero-solid card-shadow rounded-[var(--radius-card)] p-6 sm:p-7" style={{ color: "var(--color-brand-dark)" }}>
      {eyebrow && <p className="text-xs font-semibold uppercase tracking-wide" style={{ color: "var(--color-brand-dark)", opacity: 0.75 }}>{eyebrow}</p>}
      {title && <p className="mt-2 text-2xl font-bold leading-snug sm:text-[28px]">{title}</p>}
      {subtitle && <p className="mt-2 max-w-xl text-sm" style={{ opacity: 0.85 }}>{subtitle}</p>}
      {actions && <div className="mt-5 flex flex-wrap gap-2.5">{actions}</div>}
    </div>
  );
}

export function HeroLink({ to, children }) {
  return (
    <Link
      to={to}
      className="rounded-xl px-4 py-2 text-sm font-semibold transition-colors"
      style={{ background: "rgba(22, 48, 31, 0.14)", color: "var(--color-brand-dark)" }}
      onMouseEnter={(e) => (e.currentTarget.style.background = "rgba(22, 48, 31, 0.22)")}
      onMouseLeave={(e) => (e.currentTarget.style.background = "rgba(22, 48, 31, 0.14)")}
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
  const sharePct = (n) => (total === 0 ? null : Math.round((n / total) * 100));
  return (
    <div className="flex flex-wrap items-center gap-6">
      <div className="relative h-32 w-32 shrink-0">
        <svg viewBox="0 0 36 36" className="h-32 w-32 -rotate-90" role="img" aria-label="Share of facilities by agreement status">
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
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-xl font-bold leading-none" style={{ color: "var(--color-text)" }}>{total}</span>
          <span className="mt-1 text-[11px] font-medium uppercase tracking-wide" style={{ color: "var(--color-text-muted)" }}>Facilities</span>
        </div>
      </div>
      <div className="min-w-[160px] flex-1 space-y-3 text-sm">
        {segs.map(([name, n, color]) => {
          const p = sharePct(n);
          return (
            <div key={name} className="flex items-center justify-between gap-3">
              <span className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: color }} />
                <span style={{ color: "var(--color-text-secondary)" }}>{FLAG_TEXT[name]}</span>
              </span>
              <span style={{ color: "var(--color-text)" }}>
                <span className="font-semibold">{n}</span>
                {p !== null && <span className="ml-1.5 text-xs" style={{ color: "var(--color-text-muted)" }}>({p}%)</span>}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// A stacked horizontal bar of the three divergence flags. Each segment is a real link to Triage
// pre-filtered to that flag (?flag=...), using only the E4 flag parameter CONTRACT.md defines.
export function ClickableDivergenceBar({ agreement, mild, flagged }) {
  const total = agreement + mild + flagged;
  const segs = [
    ["AGREEMENT", agreement],
    ["MILD", mild],
    ["FLAGGED", flagged],
  ];
  if (total === 0) return null;
  return (
    <div>
      <div className="flex h-3.5 w-full overflow-hidden rounded-full" style={{ background: "var(--color-border)" }}>
        {segs.map(([flag, n]) => {
          if (n === 0) return null;
          const s = FLAG_STATUS[flag];
          return (
            <Link
              key={flag}
              to={`/facilities?flag=${flag}`}
              title={`${FLAG_TEXT[flag]}: ${n} facilities. View in Triage.`}
              aria-label={`${FLAG_TEXT[flag]}, ${n} facilities. View in Triage.`}
              className="h-full transition-opacity hover:opacity-80 focus-visible:opacity-80"
              style={{ width: `${(n / total) * 100}%`, background: s.dot }}
            />
          );
        })}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1.5 text-xs">
        {segs.map(([flag, n]) => {
          const s = FLAG_STATUS[flag];
          return (
            <Link key={flag} to={`/facilities?flag=${flag}`} className="flex items-center gap-1.5 hover:underline" style={{ color: "var(--color-text-secondary)" }}>
              <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: s.dot }} />
              {FLAG_TEXT[flag]} ({n})
            </Link>
          );
        })}
      </div>
    </div>
  );
}

// A toast notification, bottom-right, auto-dismissed by the caller. Used only to confirm an API
// write already succeeded, never to suggest anything is updating on its own.
export function Toast({ children }) {
  return (
    <div role="status" aria-live="polite" className="fixed bottom-5 right-5 z-50 rounded-xl border px-4 py-2.5 text-sm font-medium shadow-lg animate-toast-in" style={{ background: "var(--color-brand-dark)", borderColor: "var(--color-brand-dark)", color: "#ffffff" }}>
      {children}
    </div>
  );
}

// A low-to-high bar for a confidence interval, with a tick at the point estimate. Purely a visual
// of the exact numbers already in the Ci; it adds no label text of its own (callers keep the
// existing wording next to it).
export function RangeBar({ ci: c }) {
  if (!c) return null;
  const lowPct = Math.max(0, Math.min(100, c.low * 100));
  const highPct = Math.max(0, Math.min(100, c.high * 100));
  const valuePct = Math.max(0, Math.min(100, c.value * 100));
  return (
    <div className="mt-1.5" aria-hidden="true">
      <div className="relative h-2 w-full rounded-full" style={{ background: "var(--color-border)" }}>
        <div className="absolute inset-y-0 rounded-full" style={{ left: `${lowPct}%`, width: `${Math.max(0, highPct - lowPct)}%`, background: "var(--color-brand)", opacity: 0.45 }} />
        <div className="absolute top-1/2 h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2" style={{ left: `${valuePct}%`, background: "var(--color-brand-dark)", borderColor: "var(--color-surface)" }} />
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
          <span className="w-44 shrink-0 truncate text-sm font-medium sm:w-56" style={{ color: "var(--color-text)" }} title={r.label}>{r.label}</span>
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
      <ul className="mt-1 space-y-2.5">
        {lines.map(([label, c]) => (
          <li key={label}>
            <span className="font-medium">{label}:</span> {ci(c, interval)}
            <RangeBar ci={c} />
          </li>
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

const CORE_COLS = [
  { head: "Spread", key: "spreadBps", cell: (r) => (r.spreadBps === null ? null : fixed(r.spreadBps, 0) + " bps"), sort: (r) => (r.spreadBps === null ? -Infinity : Number(r.spreadBps)) },
  { head: "FV % of par", key: "fairValuePctPar", cell: (r) => fixed(r.fairValuePctPar, 2), sort: (r) => Number(r.fairValuePctPar) },
  { head: "Principal", key: "principal", cell: (r) => usd(r.principal), sort: (r) => Number(r.principal) },
];
const DOSSIER_COLS = [
  { head: "Cost % of par", cell: (r) => (r.costPctPar === null ? null : fixed(r.costPctPar, 2)) },
  { head: "FV % of cost", cell: (r) => (r.fvPctCost === null ? null : fixed(r.fvPctCost, 2)) },
  { head: "Floor", cell: (r) => (r.floorBps === null ? null : fixed(r.floorBps, 0) + " bps") },
  { head: "PIK", cell: (r) => (r.pikBps === null ? null : fixed(r.pikBps, 0) + " bps") },
  { head: "Maturity", cell: (r) => r.maturityDate },
  { head: "Non accrual", cell: (r) => (r.nonAccrual === null ? null : r.nonAccrual ? "Yes" : "No") },
];

// The lender table: BDC, spread, FV % of par and principal are always visible and sortable (client
// side only, over the rows E5 already returned). Each row expands to show the dossier fields E5
// already includes (costPctPar, fvPctCost, floorBps, pikBps, maturityDate, nonAccrual). A null
// dossier cell reads "Not disclosed", per CONTRACT.md's dossier null exception. A column whose
// disclosed values differ across lenders is marked "differs".
export function EvidenceTable({ rows }) {
  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState(1);
  const [expanded, setExpanded] = useState(() => new Set());

  const differs = DOSSIER_COLS.map((c) => new Set(rows.map(c.cell).filter((v) => v !== null)).size > 1);

  const sorted = [...rows];
  if (sortKey) {
    const col = CORE_COLS.find((c) => c.key === sortKey);
    sorted.sort((a, b) => (col.sort(a) - col.sort(b)) * sortDir);
  }

  const toggleSort = (key) => {
    if (sortKey === key) setSortDir((d) => -d);
    else {
      setSortKey(key);
      setSortDir(1);
    }
  };
  const toggleRow = (id) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr style={{ color: "var(--color-text-secondary)" }}>
            <th className="w-8 py-2 pr-2" />
            <th className="py-2 pr-4 font-medium">BDC</th>
            {CORE_COLS.map((c) => (
              <th key={c.key} className="py-2 pr-4 font-medium">
                <button type="button" className="flex items-center gap-1 hover:underline focus-visible:underline" style={{ color: "inherit" }} onClick={() => toggleSort(c.key)} aria-label={`Sort by ${c.head}`}>
                  {c.head}
                  {sortKey === c.key && <span aria-hidden="true">{sortDir === 1 ? "↑" : "↓"}</span>}
                </button>
              </th>
            ))}
            <th className="py-2 pr-4 font-medium">Source</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((r) => {
            const id = r.bdcName + r.sourceUrl;
            const isOpen = expanded.has(id);
            return (
              <Fragment key={id}>
                <tr className="table-row-hover border-t transition-colors" style={{ borderColor: "var(--color-border)" }}>
                  <td className="py-2 pr-2">
                    <button
                      type="button"
                      onClick={() => toggleRow(id)}
                      aria-expanded={isOpen}
                      aria-label={isOpen ? `Hide evidence dossier for ${r.bdcName}` : `Show evidence dossier for ${r.bdcName}`}
                      className="flex h-6 w-6 items-center justify-center rounded-md transition-transform"
                      style={{ color: "var(--color-text-secondary)", transform: isOpen ? "rotate(90deg)" : "none" }}
                    >
                      <svg width="14" height="14" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                        <path d="M7 4 13 10 7 16" />
                      </svg>
                    </button>
                  </td>
                  <td className="py-2.5 pr-4 font-medium" style={{ color: "var(--color-text)" }}>{r.bdcName}</td>
                  {CORE_COLS.map((c) => (
                    <td key={c.key} className="py-2.5 pr-4" style={{ color: "var(--color-text)" }}>{c.cell(r)}</td>
                  ))}
                  <td className="py-2.5 pr-4"><SourceLink url={r.sourceUrl} /></td>
                </tr>
                {isOpen && (
                  <tr className="border-t" style={{ borderColor: "var(--color-border)", background: "var(--color-brand-light)" }}>
                    <td className="p-3" />
                    <td colSpan={CORE_COLS.length + 2} className="p-3">
                      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
                        {DOSSIER_COLS.map((c, i) => {
                          const v = c.cell(r);
                          return (
                            <div key={c.head}>
                              <dt className="text-xs font-medium uppercase tracking-wide" style={{ color: "var(--color-text-muted)" }}>
                                {c.head}{differs[i] && <span className="ml-1 normal-case" style={{ color: "var(--color-flagged)" }}>differs</span>}
                              </dt>
                              <dd className="mt-0.5" style={{ color: "var(--color-text)" }}>{v === null ? NOT_DISCLOSED : v}</dd>
                            </div>
                          );
                        })}
                      </dl>
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
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
